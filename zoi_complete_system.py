"""
=============================================================================
ZOI SENTINEL v4.2 - Zero Database Architecture
REAL Manus AI Integration + Intelligent Fallback
=============================================================================

Fluxo de pesquisa:
1. Cliente pede produto → verifica cache
2. Se não tem cache → retorna dados de referência + dispara pesquisa Manus
3. Manus pesquisa nos portais reais (MAPA, ANVISA, EUR-Lex, RASFF)
4. Resultado fica em cache para próximas requisições
5. Cliente pode forçar refresh via /refresh endpoint

A API do Manus é ASSÍNCRONA:
- POST /v1/tasks → cria task, retorna task_id
- GET /v1/tasks/{task_id} → poll status (pending/running/completed/failed)
- Resultado vem quando status = completed
=============================================================================
"""

import os
import io
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

# ============================================================================
# LOGGING
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - ZOI_SENTINEL_V4 - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ZOI_SENTINEL_V4")

# ============================================================================
# APP
# ============================================================================
app = FastAPI(
    title="ZOI Sentinel v4.2 - Trade Advisory",
    description="Zero Database Architecture - Real-time Manus AI Compliance Research",
    version="4.2.0"
)

# ============================================================================
# CORS (DEVE SER O PRIMEIRO MIDDLEWARE)
# ============================================================================
LOVABLE_PROJECT_ID = os.environ.get(
    "LOVABLE_PROJECT_ID",
    "c3f2427f-f2dc-48b6-a9da-a99a6d34fdff"
)

ALLOWED_ORIGINS = [
    f"https://{LOVABLE_PROJECT_ID}.lovableproject.com",
    f"https://preview--{LOVABLE_PROJECT_ID}.lovableproject.com",
    "https://zoi-trade-navigator.lovable.app",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
]

extra_origins = os.environ.get("EXTRA_CORS_ORIGINS", "")
if extra_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-ZOI-Version"],
    max_age=3600,
)


# ============================================================================
# CONFIGURATION
# ============================================================================
MANUS_API_KEY = os.environ.get("MANUS_API_KEY", "")
MANUS_BASE_URL = "https://api.manus.ai/v1"
MANUS_AGENT_PROFILE = os.environ.get("MANUS_AGENT_PROFILE", "manus-1.6")

# Cache TTL
CACHE_TTL_HOURS = int(os.environ.get("CACHE_TTL_HOURS", "24"))

# Manus polling config
MANUS_POLL_INTERVAL = 5       # seconds between polls
MANUS_POLL_MAX_WAIT = 180     # max seconds to wait (3 min)


# ============================================================================
# IN-MEMORY CACHE
# ============================================================================
PRODUCT_CACHE: Dict[str, Dict[str, Any]] = {}
MANUS_TASKS: Dict[str, Dict[str, Any]] = {}  # track ongoing Manus tasks per product


def get_cached(slug: str) -> Optional[Dict]:
    if slug in PRODUCT_CACHE:
        cached = PRODUCT_CACHE[slug]
        try:
            cached_time = datetime.fromisoformat(cached.get("last_updated", "2000-01-01"))
            if datetime.now() - cached_time < timedelta(hours=CACHE_TTL_HOURS):
                return cached
        except Exception:
            pass
        del PRODUCT_CACHE[slug]
    return None


def set_cached(slug: str, data: Dict):
    data["last_updated"] = datetime.now().isoformat()
    PRODUCT_CACHE[slug] = data


# ============================================================================
# MANUS AI - REAL INTEGRATION
# ============================================================================

def build_compliance_prompt(product_name: str) -> str:
    """
    Prompt otimizado para o Manus pesquisar compliance de exportação.
    O Manus vai navegar nos sites reais e extrair informações.
    """
    return f"""Pesquise informações COMPLETAS e ATUALIZADAS de compliance para exportação do seguinte produto:

PRODUTO: {product_name}
ROTA COMERCIAL: Brasil → Itália (União Europeia)

PESQUISE NOS SEGUINTES PORTAIS OFICIAIS:
1. MAPA (mapa.gov.br) - requisitos fitossanitários, certificações necessárias
2. ANVISA (anvisa.gov.br) - regulamentações sanitárias aplicáveis
3. Receita Federal / SISCOMEX - código NCM correto para este produto
4. EUR-Lex (eur-lex.europa.eu) - regulamentos UE aplicáveis para importação
5. RASFF Portal (webgate.ec.europa.eu/rasff-window) - alertas recentes para este produto do Brasil
6. AGROSTAT / Comex Stat - dados de exportação recentes

RETORNE AS INFORMAÇÕES NO SEGUINTE FORMATO JSON (APENAS o JSON, sem texto adicional):
{{
    "ncm_code": "código NCM do produto (ex: 1201.90.00)",
    "product_name": "nome oficial do produto",
    "product_name_it": "nome em italiano",
    "product_name_en": "nome em inglês",
    "category": "categoria (ex: Grãos, Frutas, Bebidas)",
    "risk_score": número de 0 a 100 (100 = baixo risco, seguro para exportar),
    "risk_level": "LOW ou MEDIUM ou HIGH",
    "status": "APPROVED ou RESTRICTED ou BLOCKED",
    "certificates_required": [
        {{"name": "nome do certificado", "issuer": "órgão emissor", "mandatory": true/false}}
    ],
    "eu_regulations": [
        {{"code": "número do regulamento", "title": "título/descrição", "status": "active"}}
    ],
    "brazilian_requirements": ["lista de requisitos brasileiros"],
    "max_residue_limits": {{
        "substância": {{"limit": "limite máximo", "regulation": "regulamento"}}
    }},
    "tariff_info": {{
        "eu_tariff": "tarifa aplicável",
        "notes": "observações sobre tarifa"
    }},
    "alerts": ["alertas do RASFF ou avisos importantes"],
    "export_volume_2024": "volume exportado em 2024 se disponível",
    "sources_consulted": ["URLs dos portais consultados"]
}}

IMPORTANTE: 
- Use APENAS dados oficiais e atualizados
- Se não encontrar alguma informação, indique "Dados não disponíveis"
- O risk_score deve refletir a realidade regulatória atual
- Inclua TODOS os certificados necessários, não apenas os principais"""


async def manus_create_task(product_name: str) -> Optional[str]:
    """
    Cria uma task no Manus AI para pesquisar compliance.
    Retorna o task_id ou None se falhar.
    
    API: POST https://api.manus.ai/v1/tasks
    Headers: API_KEY: <key>
    Body: {"prompt": "...", "agentProfile": "manus-1.6"}
    Response: {"task_id": "...", "task_title": "...", "task_url": "..."}
    """
    if not MANUS_API_KEY:
        logger.warning("⚠️ MANUS_API_KEY not configured")
        return None

    prompt = build_compliance_prompt(product_name)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MANUS_BASE_URL}/tasks",
                headers={
                    "API_KEY": MANUS_API_KEY,
                    "Content-Type": "application/json",
                    "accept": "application/json",
                },
                json={
                    "prompt": prompt,
                    "agentProfile": MANUS_AGENT_PROFILE,
                    "taskMode": "agent",
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                task_id = data.get("task_id")
                logger.info(f"✅ Manus task created: {task_id}")
                logger.info(f"   Task URL: {data.get('task_url', 'N/A')}")
                return task_id
            else:
                logger.error(f"❌ Manus create task failed: {response.status_code} - {response.text}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Manus API error: {e}")
        return None


async def manus_get_task(task_id: str) -> Optional[Dict]:
    """
    Busca o status/resultado de uma task do Manus.
    
    API: GET https://api.manus.ai/v1/tasks/{task_id}
    Headers: API_KEY: <key>
    Response inclui status: pending, running, completed, failed
    """
    if not MANUS_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{MANUS_BASE_URL}/tasks/{task_id}",
                headers={
                    "API_KEY": MANUS_API_KEY,
                    "accept": "application/json",
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"❌ Manus get task failed: {response.status_code}")
                return None
                
    except Exception as e:
        logger.error(f"❌ Manus poll error: {e}")
        return None


async def manus_poll_until_complete(task_id: str) -> Optional[Dict]:
    """
    Poll a Manus task até completar ou timeout.
    Retorna o resultado da task ou None.
    """
    elapsed = 0
    
    while elapsed < MANUS_POLL_MAX_WAIT:
        task_data = await manus_get_task(task_id)
        
        if task_data is None:
            return None
        
        status = task_data.get("status", "unknown")
        logger.info(f"📊 Manus task {task_id}: status={status} (elapsed={elapsed}s)")
        
        if status == "completed":
            logger.info(f"✅ Manus task completed: {task_id}")
            return task_data
        elif status == "failed":
            logger.error(f"❌ Manus task failed: {task_id}")
            return None
        elif status in ("error",):
            logger.error(f"❌ Manus task error: {task_id}")
            return None
        
        # Still pending/running, wait and poll again
        await asyncio.sleep(MANUS_POLL_INTERVAL)
        elapsed += MANUS_POLL_INTERVAL
    
    logger.warning(f"⏰ Manus task timeout after {MANUS_POLL_MAX_WAIT}s: {task_id}")
    return None


def extract_json_from_manus_result(task_data: Dict) -> Optional[Dict]:
    """
    Extrai o JSON de compliance do resultado do Manus.
    O Manus pode retornar o resultado em diferentes campos.
    """
    # Tentar extrair de diferentes campos possíveis
    text_content = ""
    
    # O resultado pode estar em 'output', 'result', 'message', ou 'content'
    for field in ["output", "result", "message", "content", "response"]:
        if field in task_data and task_data[field]:
            val = task_data[field]
            if isinstance(val, str):
                text_content = val
                break
            elif isinstance(val, dict):
                return val
            elif isinstance(val, list):
                # Pode ser lista de messages
                for item in val:
                    if isinstance(item, dict):
                        txt = item.get("text", "") or item.get("content", "")
                        if txt:
                            text_content = txt
                            break
    
    if not text_content:
        # Tentar serializar tudo e procurar JSON dentro
        text_content = json.dumps(task_data, default=str)
    
    # Tentar extrair JSON do texto
    try:
        # Procurar bloco JSON no texto
        import re
        
        # Tentar encontrar JSON entre ```json ... ``` ou { ... }
        json_patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text_content, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and any(k in parsed for k in ["ncm_code", "product_name", "risk_score"]):
                        return parsed
                except json.JSONDecodeError:
                    continue
        
        # Último recurso: tentar parsear o texto inteiro como JSON
        return json.loads(text_content)
        
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"⚠️ Could not extract JSON from Manus result: {e}")
        return None


async def research_product_via_manus(product_slug: str, product_name: str) -> Optional[Dict]:
    """
    Fluxo completo: criar task → poll → extrair resultado.
    """
    logger.info(f"📡 MANUS RESEARCH START: {product_name}")
    
    # 1. Criar task
    task_id = await manus_create_task(product_name)
    if not task_id:
        return None
    
    # Registrar task em andamento
    MANUS_TASKS[product_slug] = {
        "task_id": task_id,
        "status": "running",
        "started_at": datetime.now().isoformat(),
    }
    
    # 2. Poll até completar
    task_result = await manus_poll_until_complete(task_id)
    
    if task_result is None:
        MANUS_TASKS[product_slug]["status"] = "timeout"
        return None
    
    # 3. Extrair JSON
    compliance_data = extract_json_from_manus_result(task_result)
    
    if compliance_data:
        # Enriquecer com metadados
        compliance_data["data_source"] = "manus_ai_realtime"
        compliance_data["manus_task_id"] = task_id
        compliance_data["needs_ai_update"] = False
        compliance_data["last_updated"] = datetime.now().isoformat()
        compliance_data["trade_route"] = compliance_data.get("trade_route", {
            "origin": "BR", "destination": "IT",
            "origin_name": "Brasil", "destination_name": "Itália"
        })
        
        MANUS_TASKS[product_slug]["status"] = "completed"
        logger.info(f"✅ MANUS RESEARCH COMPLETE: {product_name}")
        return compliance_data
    
    MANUS_TASKS[product_slug]["status"] = "parse_error"
    logger.warning(f"⚠️ Manus completed but could not parse result for: {product_name}")
    return None


# ============================================================================
# BACKGROUND RESEARCH (não bloqueia a resposta ao cliente)
# ============================================================================

async def background_manus_research(product_slug: str, product_name: str):
    """
    Executa pesquisa Manus em background.
    O cliente recebe resposta imediata com dados de referência.
    Quando Manus completar, o cache é atualizado.
    """
    try:
        result = await research_product_via_manus(product_slug, product_name)
        if result:
            set_cached(product_slug, result)
            logger.info(f"🔄 Background research cached: {product_slug}")
    except Exception as e:
        logger.error(f"❌ Background research error for {product_slug}: {e}")


# ============================================================================
# KNOWLEDGE BASE (fallback quando Manus não disponível)
# ============================================================================

REFERENCE_DATA = {
    "soja_grao": {
        "ncm_code": "1201.90.00",
        "product_name": "Soja em Grãos",
        "product_name_it": "Semi di Soia",
        "product_name_en": "Soybeans",
        "category": "Grãos e Cereais",
        "risk_score": 100,
        "risk_level": "LOW",
        "status": "ZOI APPROVED",
        "trade_route": {"origin": "BR", "destination": "IT", "origin_name": "Brasil", "destination_name": "Itália"},
        "certificates_required": [
            {"name": "Certificado Fitossanitário", "issuer": "MAPA", "mandatory": True},
            {"name": "Certificado de Origem", "issuer": "Câmara de Comércio", "mandatory": True},
            {"name": "Bill of Lading", "issuer": "Transportadora", "mandatory": True},
            {"name": "Commercial Invoice", "issuer": "Exportador", "mandatory": True},
            {"name": "Packing List", "issuer": "Exportador", "mandatory": True},
            {"name": "Certificado de Fumigação", "issuer": "Empresa certificada", "mandatory": False},
        ],
        "eu_regulations": [
            {"code": "Reg. (CE) 178/2002", "title": "Segurança alimentar geral", "status": "active"},
            {"code": "Reg. (CE) 1881/2006", "title": "Limites de contaminantes em alimentos", "status": "active"},
            {"code": "Reg. (UE) 2023/915", "title": "Limites de micotoxinas", "status": "active"},
            {"code": "Reg. (CE) 1829/2003", "title": "Alimentos geneticamente modificados", "status": "active"},
        ],
        "brazilian_requirements": [
            "Registro no MAPA como exportador de grãos",
            "Certificado fitossanitário emitido pelo SDA/MAPA",
            "Análise de resíduos de pesticidas (LMR conforme Codex)",
            "Análise de micotoxinas (aflatoxinas B1, B2, G1, G2)",
            "Declaração de OGM/não-OGM conforme Reg. 1829/2003",
        ],
        "max_residue_limits": {
            "aflatoxinas_total": {"limit": "4 µg/kg", "regulation": "Reg. 1881/2006"},
            "aflatoxina_b1": {"limit": "2 µg/kg", "regulation": "Reg. 1881/2006"},
            "glifosato": {"limit": "20 mg/kg", "regulation": "Reg. 396/2005"},
        },
        "tariff_info": {"eu_tariff": "0%", "notes": "Tarifa zero para soja em grãos"},
        "alerts": [],
        "risk_factors": {
            "documentation": {"score": 100, "level": "LOW"},
            "regulatory": {"score": 95, "level": "LOW"},
            "logistics": {"score": 90, "level": "LOW"},
            "market_access": {"score": 100, "level": "LOW"},
        },
    },
    "acai": {
        "ncm_code": "0810.90.00",
        "product_name": "Açaí (Polpa/Fruto)",
        "product_name_it": "Açaí (Polpa/Frutto)",
        "product_name_en": "Açaí Berry (Pulp/Fruit)",
        "category": "Frutas Tropicais",
        "risk_score": 85,
        "risk_level": "LOW",
        "status": "ZOI APPROVED",
        "trade_route": {"origin": "BR", "destination": "IT", "origin_name": "Brasil", "destination_name": "Itália"},
        "certificates_required": [
            {"name": "Certificado Fitossanitário", "issuer": "MAPA", "mandatory": True},
            {"name": "Certificado Sanitário", "issuer": "ANVISA/SIF", "mandatory": True},
            {"name": "Certificado de Origem", "issuer": "Câmara de Comércio", "mandatory": True},
            {"name": "Laudo Microbiológico", "issuer": "Laboratório acreditado", "mandatory": True},
            {"name": "Análise de Resíduos", "issuer": "Laboratório acreditado", "mandatory": True},
        ],
        "eu_regulations": [
            {"code": "Reg. (CE) 178/2002", "title": "Segurança alimentar geral", "status": "active"},
            {"code": "Reg. (CE) 396/2005", "title": "Limites máximos de resíduos de pesticidas", "status": "active"},
            {"code": "Reg. (UE) 1169/2011", "title": "Rotulagem de alimentos", "status": "active"},
            {"code": "Reg. (CE) 852/2004", "title": "Higiene dos gêneros alimentícios", "status": "active"},
        ],
        "brazilian_requirements": [
            "Registro no MAPA/SIF",
            "Boas Práticas de Fabricação (BPF/GMP)",
            "Certificado fitossanitário",
            "Controle de cadeia fria (-18°C para polpa congelada)",
            "APPCC/HACCP implementado",
        ],
        "max_residue_limits": {},
        "tariff_info": {"eu_tariff": "8.8%", "notes": "Tarifa para frutas tropicais"},
        "alerts": ["⚠️ Atenção à cadeia fria - açaí é altamente perecível"],
        "risk_factors": {
            "documentation": {"score": 85, "level": "LOW"},
            "regulatory": {"score": 80, "level": "MEDIUM"},
            "logistics": {"score": 75, "level": "MEDIUM"},
            "market_access": {"score": 90, "level": "LOW"},
        },
    },
    "cafe": {
        "ncm_code": "0901.11.00",
        "product_name": "Café Verde (Grãos não torrados)",
        "product_name_it": "Caffè Verde",
        "product_name_en": "Green Coffee Beans",
        "category": "Bebidas",
        "risk_score": 95,
        "risk_level": "LOW",
        "status": "ZOI APPROVED",
        "trade_route": {"origin": "BR", "destination": "IT", "origin_name": "Brasil", "destination_name": "Itália"},
        "certificates_required": [
            {"name": "Certificado Fitossanitário", "issuer": "MAPA", "mandatory": True},
            {"name": "Certificado de Origem", "issuer": "Câmara de Comércio", "mandatory": True},
            {"name": "ICO Certificate of Origin", "issuer": "CECAFÉ", "mandatory": True},
        ],
        "eu_regulations": [
            {"code": "Reg. (CE) 178/2002", "title": "Segurança alimentar geral", "status": "active"},
            {"code": "Reg. (CE) 1881/2006", "title": "Limites de contaminantes", "status": "active"},
            {"code": "Reg. (UE) 2023/1115", "title": "EUDR - Regulamento anti-desmatamento", "status": "active"},
        ],
        "brazilian_requirements": [
            "Registro no CECAFÉ",
            "Classificação oficial do café",
            "Due Diligence EUDR - rastreabilidade até a fazenda",
        ],
        "max_residue_limits": {
            "ocratoxina_a": {"limit": "5 µg/kg (torrado)", "regulation": "Reg. 1881/2006"},
        },
        "tariff_info": {"eu_tariff": "0%", "notes": "Café verde com tarifa zero na UE"},
        "alerts": ["🌿 EUDR: obrigatória due diligence anti-desmatamento"],
        "risk_factors": {
            "documentation": {"score": 95, "level": "LOW"},
            "regulatory": {"score": 90, "level": "LOW"},
            "logistics": {"score": 95, "level": "LOW"},
            "market_access": {"score": 100, "level": "LOW"},
        },
    },
}

SLUG_ALIASES = {
    "soja": "soja_grao", "soja_graos": "soja_grao", "soybeans": "soja_grao",
    "açaí": "acai", "açai": "acai", "acai_polpa": "acai",
    "coffee": "cafe", "café": "cafe", "cafe_verde": "cafe",
}


def normalize_slug(slug: str) -> str:
    normalized = slug.lower().strip().replace("-", "_").replace(" ", "_")
    return SLUG_ALIASES.get(normalized, normalized)


def make_unknown_product_template(product_name: str) -> Dict:
    """Template para produto desconhecido - NUNCA retorna 404."""
    return {
        "ncm_code": "PESQUISA_EM_ANDAMENTO",
        "product_name": product_name,
        "product_name_it": product_name,
        "product_name_en": product_name,
        "category": "Classificação via IA em andamento",
        "risk_score": 50,
        "risk_level": "PENDING",
        "status": "RESEARCHING",
        "trade_route": {"origin": "BR", "destination": "IT", "origin_name": "Brasil", "destination_name": "Itália"},
        "certificates_required": [
            {"name": "Certificado Fitossanitário", "issuer": "MAPA", "mandatory": True},
            {"name": "Certificado de Origem", "issuer": "Câmara de Comércio", "mandatory": True},
        ],
        "eu_regulations": [
            {"code": "Reg. (CE) 178/2002", "title": "Segurança alimentar geral", "status": "active"},
        ],
        "brazilian_requirements": ["Verificar requisitos específicos no MAPA"],
        "max_residue_limits": {},
        "tariff_info": {"eu_tariff": "Verificar", "notes": "Consultar TARIC"},
        "alerts": [
            f"🔍 Pesquisa IA em andamento para '{product_name}'...",
            "Os dados serão atualizados automaticamente quando a pesquisa completar.",
            "Você também pode clicar 'Atualizar via IA' para verificar.",
        ],
        "risk_factors": {
            "documentation": {"score": 50, "level": "PENDING"},
            "regulatory": {"score": 50, "level": "PENDING"},
            "logistics": {"score": 50, "level": "PENDING"},
            "market_access": {"score": 50, "level": "PENDING"},
        },
        "data_source": "template_pending_research",
        "needs_ai_update": True,
    }


# ============================================================================
# CORE: GET PRODUCT DATA
# ============================================================================

async def get_product_data(
    product_slug: str,
    force_refresh: bool = False,
    background_tasks: Optional[BackgroundTasks] = None,
) -> Dict:
    """
    Obtém dados de compliance. Hierarquia:
    1. Cache (se válido e não forçando refresh)
    2. Manus AI em tempo real (pesquisa síncrona se refresh)
    3. Knowledge base + dispara Manus em background
    4. Template genérico + dispara Manus em background
    """
    slug = normalize_slug(product_slug)
    product_name = product_slug.replace("_", " ").replace("-", " ").title()

    # 1. Cache
    if not force_refresh:
        cached = get_cached(slug)
        if cached:
            cached["data_source_note"] = "Dados em cache"
            return cached

    # 2. Se refresh forçado ou Manus disponível, pesquisar SÍNCRONAMENTE
    if force_refresh and MANUS_API_KEY:
        logger.info(f"🔄 Forced refresh via Manus: {product_name}")
        manus_result = await research_product_via_manus(slug, product_name)
        if manus_result:
            set_cached(slug, manus_result)
            return manus_result

    # 3. Knowledge base (resposta imediata)
    if slug in REFERENCE_DATA:
        data = {**REFERENCE_DATA[slug]}
        data["data_source"] = "reference_knowledge"
        data["needs_ai_update"] = True
        data["last_updated"] = datetime.now().isoformat()
        data["data_source_note"] = "Dados de referência. Pesquisa IA em andamento..."
        
        # Disparar Manus em BACKGROUND (não bloqueia resposta)
        if MANUS_API_KEY and background_tasks:
            background_tasks.add_task(background_manus_research, slug, product_name)
            data["manus_research_status"] = "started_in_background"
        
        set_cached(slug, data)
        return data

    # 4. Produto DESCONHECIDO - template + Manus background
    data = make_unknown_product_template(product_name)
    data["last_updated"] = datetime.now().isoformat()
    
    if MANUS_API_KEY and background_tasks:
        background_tasks.add_task(background_manus_research, slug, product_name)
        data["manus_research_status"] = "started_in_background"
        data["alerts"][0] = f"🔍 Pesquisa IA iniciada para '{product_name}' via Manus AI..."
    elif not MANUS_API_KEY:
        data["alerts"].append("⚠️ Manus AI não configurado. Configure MANUS_API_KEY no Render.")
    
    return data


# ============================================================================
# PDF GENERATION
# ============================================================================

def generate_compliance_pdf(product: Dict) -> bytes:
    """Gera PDF de compliance profissional."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4

        GREEN = HexColor("#0F7A3F")
        DARK = HexColor("#1a1a2e")
        GRAY = HexColor("#666666")

        # Header
        c.setFillColor(GREEN)
        c.rect(0, h - 2.5*cm, w, 2.5*cm, fill=1)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 22)
        c.drawString(2*cm, h - 1.7*cm, "ZOI Sentinel")
        c.setFont("Helvetica", 10)
        c.drawString(2*cm, h - 2.2*cm, "Trade Compliance Intelligence Report")
        c.drawRightString(w - 2*cm, h - 1.7*cm, datetime.now().strftime("%d/%m/%Y %H:%M"))

        # Product
        y = h - 4.5*cm
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 26)
        c.drawString(2*cm, y, product.get("product_name", "Produto"))

        y -= 1*cm
        c.setFont("Helvetica", 12)
        c.setFillColor(GRAY)
        c.drawString(2*cm, y, f"NCM: {product.get('ncm_code', 'N/A')}")
        route = product.get("trade_route", {})
        c.drawString(10*cm, y, f"Rota: {route.get('origin_name', 'BR')} → {route.get('destination_name', 'IT')}")

        y -= 0.8*cm
        score = product.get("risk_score", 50)
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y, f"Risk Score: {score}/100")
        c.drawString(8*cm, y, f"Status: {product.get('status', 'N/A')}")

        # Sections helper
        def draw_section(y_pos, title, items, format_fn):
            if y_pos < 5*cm:
                c.showPage()
                y_pos = h - 3*cm
            y_pos -= 1.5*cm
            c.setFillColor(DARK)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(2*cm, y_pos, title)
            y_pos -= 0.3*cm
            c.setStrokeColor(GREEN)
            c.setLineWidth(1.5)
            c.line(2*cm, y_pos, 8*cm, y_pos)
            y_pos -= 0.6*cm
            c.setFont("Helvetica", 10)
            c.setFillColor(DARK)
            for item in items:
                text = format_fn(item)
                if y_pos < 2.5*cm:
                    c.showPage()
                    y_pos = h - 3*cm
                c.drawString(2.5*cm, y_pos, f"• {text[:85]}")
                y_pos -= 0.5*cm
            return y_pos

        # Certificates
        certs = product.get("certificates_required", [])
        y = draw_section(y, "Certificados Necessários", certs,
            lambda x: f"{x['name']} ({x['issuer']})" if isinstance(x, dict) else str(x))

        # EU Regulations
        regs = product.get("eu_regulations", [])
        y = draw_section(y, "Regulamentos UE", regs,
            lambda x: f"{x['code']} - {x['title']}" if isinstance(x, dict) else str(x))

        # Brazilian Requirements
        br_reqs = product.get("brazilian_requirements", [])
        y = draw_section(y, "Requisitos Brasileiros", br_reqs, lambda x: str(x))

        # MRL
        mrl = product.get("max_residue_limits", {})
        if mrl:
            mrl_list = [{"name": k, "info": v} for k, v in mrl.items()]
            y = draw_section(y, "Limites Máximos de Resíduos", mrl_list,
                lambda x: f"{x['name'].replace('_',' ').title()}: {x['info'].get('limit','N/A') if isinstance(x['info'],dict) else x['info']}")

        # Alerts
        alerts = product.get("alerts", [])
        if alerts:
            y = draw_section(y, "Alertas", alerts, lambda x: str(x)[:85])

        # Footer
        source = product.get("data_source", "unknown")
        source_labels = {
            "manus_ai_realtime": "Pesquisa IA em Tempo Real (Manus AI)",
            "reference_knowledge": "Base de Referência",
            "cache": "Cache",
            "template_pending_research": "Template (pesquisa pendente)",
        }
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 7)
        c.drawString(1.5*cm, 1*cm,
            f"ZOI Sentinel v4.2 | Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')} | "
            f"Fonte: {source_labels.get(source, source)}")
        c.drawRightString(w - 1.5*cm, 1*cm, "© ZOI Trade Advisory")

        c.save()
        return buffer.getvalue()

    except ImportError:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 22)
        pdf.cell(0, 12, "ZOI Sentinel - Compliance Report", ln=True)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, product.get("product_name", "Produto"), ln=True)
        pdf.cell(0, 7, f"NCM: {product.get('ncm_code', 'N/A')}", ln=True)
        pdf.cell(0, 7, f"Risk Score: {product.get('risk_score', 'N/A')}/100", ln=True)
        pdf.cell(0, 7, f"Status: {product.get('status', 'N/A')}", ln=True)
        return bytes(pdf.output())


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "ZOI Sentinel v4.2",
        "architecture": "zero_database",
        "ai_engine": "manus_ai",
        "manus_configured": bool(MANUS_API_KEY),
        "endpoints": {
            "get_product": "GET /api/products/{slug}",
            "export_pdf": "GET /api/products/{slug}/export-pdf",
            "refresh": "GET /api/products/{slug}/refresh",
            "list": "GET /api/products",
            "health": "GET /health",
            "research_status": "GET /api/research-status/{slug}",
        }
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "4.2.0",
        "architecture": "zero_database",
        "manus_ai": "configured" if MANUS_API_KEY else "NOT_CONFIGURED",
        "manus_profile": MANUS_AGENT_PROFILE,
        "cache_size": len(PRODUCT_CACHE),
        "active_research": len([t for t in MANUS_TASKS.values() if t.get("status") == "running"]),
        "known_products": len(REFERENCE_DATA),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/products")
async def list_products():
    products = []
    for slug, data in REFERENCE_DATA.items():
        products.append({
            "slug": slug,
            "name": data["product_name"],
            "ncm_code": data["ncm_code"],
            "category": data["category"],
            "risk_score": data["risk_score"],
            "status": data["status"],
        })
    return {
        "success": True,
        "products": products,
        "total": len(products),
        "note": "Qualquer produto pode ser pesquisado - produtos não listados serão pesquisados via Manus AI.",
    }


@app.get("/api/products/{product_slug}")
async def get_product(product_slug: str, background_tasks: BackgroundTasks):
    """Retorna dados de compliance. Dispara Manus AI em background se necessário."""
    logger.info(f"📦 PRODUCT REQUEST: {product_slug}")
    product_data = await get_product_data(product_slug, background_tasks=background_tasks)
    return {
        "success": True,
        "product": product_data,
        "architecture": "zero_database_v4",
        "ai_engine": "manus_ai" if MANUS_API_KEY else "reference_only",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/products/{product_slug}/export-pdf")
async def export_pdf(product_slug: str, background_tasks: BackgroundTasks):
    """Gera PDF de compliance."""
    logger.info(f"📄 PDF GENERATION REQUEST: {product_slug}")
    product_data = await get_product_data(product_slug, background_tasks=background_tasks)

    try:
        pdf_bytes = generate_compliance_pdf(product_data)
        safe = product_slug.replace("/", "_").replace("\\", "_")
        filename = f"ZOI_Compliance_{safe}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
    except Exception as e:
        logger.error(f"❌ PDF error: {e}", exc_info=True)
        raise HTTPException(500, detail=f"Erro ao gerar PDF: {str(e)}")


@app.get("/api/products/{product_slug}/refresh")
async def refresh_product(product_slug: str):
    """
    Força pesquisa síncrona via Manus AI.
    Espera o resultado (até 3 min) e retorna dados atualizados.
    Chamado quando usuário clica 'Atualizar via IA'.
    """
    logger.info(f"🔄 REFRESH (sync Manus): {product_slug}")
    product_data = await get_product_data(product_slug, force_refresh=True)
    return {
        "success": True,
        "product": product_data,
        "refreshed": True,
        "source": product_data.get("data_source", "unknown"),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/research-status/{product_slug}")
async def research_status(product_slug: str):
    """Verifica o status de uma pesquisa Manus em andamento."""
    slug = normalize_slug(product_slug)

    task_info = MANUS_TASKS.get(slug, {})
    cached = get_cached(slug)

    # Se tem cache com dados do Manus, pesquisa já completou
    if cached and cached.get("data_source") == "manus_ai_realtime":
        return {
            "slug": slug,
            "research_complete": True,
            "data_source": "manus_ai_realtime",
            "last_updated": cached.get("last_updated"),
        }

    return {
        "slug": slug,
        "research_complete": False,
        "manus_task": task_info,
        "has_cache": cached is not None,
        "cache_source": cached.get("data_source") if cached else None,
    }


# OPTIONS handler (safety net para CORS)
@app.options("/{rest_of_path:path}")
async def preflight(request: Request, rest_of_path: str):
    origin = request.headers.get("origin", "")
    return JSONResponse(
        content={"ok": True},
        headers={
            "Access-Control-Allow-Origin": origin if origin in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0],
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "3600",
            "Access-Control-Allow-Credentials": "true",
        }
    )


# ============================================================================
# STARTUP
# ============================================================================

@app.on_event("startup")
async def startup():
    logger.info("=" * 70)
    logger.info("🚀 ZOI SENTINEL v4.2 - Zero Database + Manus AI")
    logger.info(f"📡 Manus AI: {'✅ CONFIGURED' if MANUS_API_KEY else '❌ NOT CONFIGURED'}")
    logger.info(f"🤖 Agent Profile: {MANUS_AGENT_PROFILE}")
    logger.info(f"📦 Reference products: {len(REFERENCE_DATA)}")
    logger.info(f"🌐 CORS origins: {len(ALLOWED_ORIGINS)}")
    if not MANUS_API_KEY:
        logger.warning("⚠️ Configure MANUS_API_KEY no Render para ativar pesquisa em tempo real!")
    logger.info("=" * 70)


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
