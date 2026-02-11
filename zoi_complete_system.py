"""
=============================================================================
ZOI SENTINEL v4.2 - Zero Database Architecture
Trade Compliance Intelligence System
Backend FastAPI - CORRIGIDO E PRONTO PARA DEPLOY
=============================================================================
"""

import os
import io
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
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
# APP INITIALIZATION
# ============================================================================
app = FastAPI(
    title="ZOI Sentinel v4.2 - Trade Advisory",
    description="Zero Database Architecture - Real-time AI Compliance Research",
    version="4.2.0"
)

# ============================================================================
# CORS - MUST BE FIRST MIDDLEWARE (antes de qualquer rota!)
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

# Adicionar origins extras do environment se existirem
extra_origins = os.environ.get("EXTRA_CORS_ORIGINS", "")
if extra_origins:
    ALLOWED_ORIGINS.extend(extra_origins.split(","))

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
# IN-MEMORY CACHE (substitui banco de dados)
# ============================================================================
# Cache temporário em memória - não é banco de dados estático!
# Dados expiram e são renovados via pesquisa IA
PRODUCT_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_HOURS = 24  # Cache expira em 24 horas

def get_cached_product(slug: str) -> Optional[Dict]:
    """Retorna produto do cache se ainda válido."""
    if slug in PRODUCT_CACHE:
        cached = PRODUCT_CACHE[slug]
        cached_time = datetime.fromisoformat(cached.get("last_updated", "2000-01-01"))
        if datetime.now() - cached_time < timedelta(hours=CACHE_TTL_HOURS):
            logger.info(f"📦 Cache hit: {slug}")
            return cached
        else:
            logger.info(f"⏰ Cache expired: {slug}")
            del PRODUCT_CACHE[slug]
    return None

def set_cached_product(slug: str, data: Dict):
    """Salva produto no cache."""
    data["last_updated"] = datetime.now().isoformat()
    PRODUCT_CACHE[slug] = data

# ============================================================================
# MANUS AI / DYAD INTEGRATION
# ============================================================================
MANUS_API_URL = os.environ.get("MANUS_API_URL", "https://api.manus.ai/v1")
MANUS_API_KEY = os.environ.get("MANUS_API_KEY", "")
DYAD_API_URL = os.environ.get("DYAD_API_URL", "")
DYAD_API_KEY = os.environ.get("DYAD_API_KEY", "")

async def research_via_manus(product_name: str) -> Optional[Dict]:
    """Pesquisa compliance via Manus AI."""
    if not MANUS_API_KEY:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{MANUS_API_URL}/research",
                headers={
                    "Authorization": f"Bearer {MANUS_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "query": f"""
                    Pesquise informações completas de compliance para exportação:
                    Produto: {product_name}
                    Rota: Brasil → Itália/União Europeia
                    
                    Busque em: MAPA (mapa.gov.br), ANVISA, Receita Federal (NCM), 
                    EUR-Lex, RASFF, AGROSTAT.
                    
                    Retorne JSON com: ncm_code, product_name, risk_score (0-100),
                    certificates_required, eu_regulations, brazilian_requirements,
                    max_residue_limits, alerts, tariff_info
                    """,
                    "format": "json",
                    "sources": [
                        "mapa.gov.br", "anvisa.gov.br", 
                        "eur-lex.europa.eu", "webgate.ec.europa.eu"
                    ]
                }
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Manus AI research complete for: {product_name}")
                return data
    except Exception as e:
        logger.warning(f"⚠️ Manus AI unavailable: {e}")
    
    return None

async def research_via_dyad(product_name: str) -> Optional[Dict]:
    """Pesquisa compliance via Dyad Agent."""
    if not DYAD_API_KEY:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                f"{DYAD_API_URL}/agent/research",
                headers={
                    "Authorization": f"Bearer {DYAD_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "task": "trade_compliance_research",
                    "product": product_name,
                    "route": {"origin": "BR", "destination": "IT"},
                    "output_format": "json"
                }
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ Dyad research complete for: {product_name}")
                return data
    except Exception as e:
        logger.warning(f"⚠️ Dyad unavailable: {e}")
    
    return None

# ============================================================================
# KNOWLEDGE BASE - Dados de referência (fallback inteligente)
# ============================================================================
# Estes NÃO substituem a pesquisa IA - são fallback quando IA está indisponível

REFERENCE_KNOWLEDGE = {
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
            {"code": "Reg. (CE) 834/2007", "title": "Produção orgânica (se aplicável)", "status": "active"},
        ],
        "brazilian_requirements": [
            "Registro no MAPA como exportador de grãos",
            "Certificado fitossanitário emitido pelo SDA/MAPA",
            "Análise de resíduos de pesticidas (LMR conforme Codex)",
            "Análise de micotoxinas (aflatoxinas B1, B2, G1, G2)",
            "Declaração de OGM/não-OGM conforme Reg. 1829/2003",
            "Inspeção fitossanitária no ponto de embarque",
        ],
        "max_residue_limits": {
            "aflatoxinas_total": {"limit": "4 µg/kg", "regulation": "Reg. 1881/2006"},
            "aflatoxina_b1": {"limit": "2 µg/kg", "regulation": "Reg. 1881/2006"},
            "glifosato": {"limit": "20 mg/kg", "regulation": "Reg. 396/2005"},
            "cádmio": {"limit": "0.20 mg/kg", "regulation": "Reg. 1881/2006"},
        },
        "tariff_info": {
            "eu_tariff": "0%",
            "notes": "Tarifa zero para soja em grãos do Brasil (Acordo Mercosul-UE em negociação)"
        },
        "alerts": [],
        "risk_factors": {
            "documentation": {"score": 100, "level": "LOW", "details": "Documentação padrão bem definida"},
            "regulatory": {"score": 95, "level": "LOW", "details": "Regulamentação estável e clara"},
            "logistics": {"score": 90, "level": "LOW", "details": "Rota marítima consolidada BR→IT"},
            "market_access": {"score": 100, "level": "LOW", "details": "Acesso livre ao mercado UE"},
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
            {"code": "Reg. (CE) 853/2004", "title": "Regras de higiene para alimentos de origem animal", "status": "active"},
        ],
        "brazilian_requirements": [
            "Registro no MAPA/SIF",
            "Boas Práticas de Fabricação (BPF/GMP)",
            "Certificado fitossanitário",
            "Controle de cadeia fria (-18°C para polpa congelada)",
            "APPCC/HACCP implementado",
            "Rotulagem em italiano conforme Reg. 1169/2011",
        ],
        "max_residue_limits": {
            "contaminantes_microbiológicos": {"limit": "Conforme Reg. 2073/2005", "regulation": "Reg. 2073/2005"},
        },
        "tariff_info": {
            "eu_tariff": "8.8%",
            "notes": "Tarifa aplicável para frutas tropicais frescas/congeladas"
        },
        "alerts": [
            "⚠️ Atenção especial à cadeia fria - açaí é altamente perecível",
            "📋 Rotulagem deve incluir informação nutricional em italiano"
        ],
        "risk_factors": {
            "documentation": {"score": 85, "level": "LOW", "details": "Requer documentação sanitária adicional"},
            "regulatory": {"score": 80, "level": "MEDIUM", "details": "Regulamentação específica para produtos perecíveis"},
            "logistics": {"score": 75, "level": "MEDIUM", "details": "Cadeia fria obrigatória"},
            "market_access": {"score": 90, "level": "LOW", "details": "Demanda crescente na UE"},
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
            {"name": "Certificado de Qualidade", "issuer": "ABIC/Laboratório", "mandatory": False},
        ],
        "eu_regulations": [
            {"code": "Reg. (CE) 178/2002", "title": "Segurança alimentar geral", "status": "active"},
            {"code": "Reg. (CE) 1881/2006", "title": "Limites de contaminantes", "status": "active"},
            {"code": "Reg. (UE) 2023/1115", "title": "Regulamento anti-desmatamento (EUDR)", "status": "active"},
        ],
        "brazilian_requirements": [
            "Registro no CECAFÉ",
            "Classificação oficial do café (tipo, bebida, peneira)",
            "Certificado fitossanitário MAPA",
            "Due Diligence EUDR - rastreabilidade até a fazenda",
        ],
        "max_residue_limits": {
            "ocratoxina_a": {"limit": "5 µg/kg (café torrado), 10 µg/kg (solúvel)", "regulation": "Reg. 1881/2006"},
            "acrilamida": {"limit": "400 µg/kg (café torrado)", "regulation": "Reg. 2017/2158"},
        },
        "tariff_info": {
            "eu_tariff": "0%",
            "notes": "Café verde com tarifa zero na UE"
        },
        "alerts": [
            "🌿 EUDR (Reg. 2023/1115): A partir de 2025, obrigatória due diligence anti-desmatamento"
        ],
        "risk_factors": {
            "documentation": {"score": 95, "level": "LOW", "details": "Documentação bem estabelecida via CECAFÉ"},
            "regulatory": {"score": 90, "level": "LOW", "details": "EUDR requer atenção adicional"},
            "logistics": {"score": 95, "level": "LOW", "details": "Logística madura e consolidada"},
            "market_access": {"score": 100, "level": "LOW", "details": "Itália é o maior importador europeu"},
        },
    },
}

# Aliases para slugs alternativos
SLUG_ALIASES = {
    "soja": "soja_grao",
    "soja_graos": "soja_grao",
    "soybeans": "soja_grao",
    "açaí": "acai",
    "açai": "acai",
    "acai_polpa": "acai",
    "coffee": "cafe",
    "café": "cafe",
    "cafe_verde": "cafe",
}

def normalize_slug(slug: str) -> str:
    """Normaliza o slug do produto."""
    normalized = slug.lower().strip().replace("-", "_").replace(" ", "_")
    # Resolver aliases
    return SLUG_ALIASES.get(normalized, normalized)


# ============================================================================
# CORE RESEARCH FUNCTION
# ============================================================================

async def get_product_data(product_slug: str, force_refresh: bool = False) -> Dict:
    """
    Obtém dados de compliance de um produto.
    
    Hierarquia de fontes:
    1. Cache em memória (se válido e não forçando refresh)
    2. Pesquisa via Manus AI (tempo real)
    3. Pesquisa via Dyad Agent (backup)
    4. Knowledge base de referência (fallback)
    5. Template genérico (NUNCA retorna 404)
    """
    slug = normalize_slug(product_slug)
    product_name = product_slug.replace("_", " ").replace("-", " ").title()
    
    # 1. Verificar cache
    if not force_refresh:
        cached = get_cached_product(slug)
        if cached:
            cached["data_source"] = "cache"
            return cached
    
    # 2. Tentar Manus AI
    logger.info(f"📡 Researching product: {product_name}")
    ai_data = await research_via_manus(product_name)
    if ai_data:
        ai_data["data_source"] = "manus_ai_realtime"
        set_cached_product(slug, ai_data)
        return ai_data
    
    # 3. Tentar Dyad
    dyad_data = await research_via_dyad(product_name)
    if dyad_data:
        dyad_data["data_source"] = "dyad_agent_realtime"
        set_cached_product(slug, dyad_data)
        return dyad_data
    
    # 4. Knowledge base de referência
    if slug in REFERENCE_KNOWLEDGE:
        data = {**REFERENCE_KNOWLEDGE[slug]}
        data["data_source"] = "reference_knowledge"
        data["needs_ai_update"] = True
        data["last_updated"] = datetime.now().isoformat()
        data["message"] = "Dados de referência. Clique 'Atualizar via IA' para dados em tempo real."
        set_cached_product(slug, data)
        return data
    
    # 5. Template genérico para produto DESCONHECIDO
    # NUNCA retorna 404!
    unknown_data = {
        "ncm_code": "PESQUISA_NECESSÁRIA",
        "product_name": product_name,
        "product_name_it": product_name,
        "product_name_en": product_name,
        "category": "A ser classificado via IA",
        "risk_score": 50,
        "risk_level": "PENDING",
        "status": "PENDING_RESEARCH",
        "trade_route": {"origin": "BR", "destination": "IT", "origin_name": "Brasil", "destination_name": "Itália"},
        "certificates_required": [
            {"name": "Certificado Fitossanitário", "issuer": "MAPA", "mandatory": True},
            {"name": "Certificado de Origem", "issuer": "Câmara de Comércio", "mandatory": True},
        ],
        "eu_regulations": [
            {"code": "Reg. (CE) 178/2002", "title": "Segurança alimentar geral (aplicável a todos os alimentos)", "status": "active"},
        ],
        "brazilian_requirements": [
            "Verificar requisitos específicos no MAPA para este produto"
        ],
        "max_residue_limits": {},
        "tariff_info": {"eu_tariff": "Verificar", "notes": "Consultar TARIC para NCM específico"},
        "alerts": [
            f"🔍 Produto '{product_name}' requer pesquisa completa via IA.",
            "Clique em 'Atualizar via IA' para obter dados regulatórios em tempo real.",
        ],
        "risk_factors": {
            "documentation": {"score": 50, "level": "PENDING", "details": "Pesquisa IA necessária"},
            "regulatory": {"score": 50, "level": "PENDING", "details": "Pesquisa IA necessária"},
            "logistics": {"score": 50, "level": "PENDING", "details": "Pesquisa IA necessária"},
            "market_access": {"score": 50, "level": "PENDING", "details": "Pesquisa IA necessária"},
        },
        "data_source": "template_pending_research",
        "needs_ai_update": True,
        "last_updated": datetime.now().isoformat(),
        "message": f"Produto '{product_name}' não encontrado na base de referência. "
                   "Use 'Atualizar via IA' para pesquisar dados de compliance em tempo real.",
    }
    return unknown_data


# ============================================================================
# PDF GENERATION
# ============================================================================

def generate_compliance_pdf(product: Dict) -> bytes:
    """Gera relatório PDF de compliance."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, mm
        from reportlab.lib.colors import HexColor
        from reportlab.pdfgen import canvas
        from reportlab.lib.styles import getSampleStyleSheet
        
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4
        
        # Colors
        GREEN = HexColor("#0F7A3F")
        DARK = HexColor("#1a1a2e")
        GRAY = HexColor("#666666")
        LIGHT_GREEN = HexColor("#E8F5E9")
        
        # ---- PAGE 1: Cover & Summary ----
        # Header bar
        c.setFillColor(GREEN)
        c.rect(0, h - 2.5*cm, w, 2.5*cm, fill=1)
        
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 22)
        c.drawString(2*cm, h - 1.8*cm, "ZOI Sentinel")
        c.setFont("Helvetica", 11)
        c.drawString(2*cm, h - 2.2*cm, "Trade Compliance Intelligence Report")
        
        # Date
        c.setFont("Helvetica", 9)
        c.drawRightString(w - 2*cm, h - 1.8*cm, datetime.now().strftime("%d/%m/%Y %H:%M"))
        
        # Product name
        y = h - 4.5*cm
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(2*cm, y, product.get("product_name", "Produto"))
        
        # NCM & Route
        y -= 1.2*cm
        c.setFont("Helvetica", 13)
        c.setFillColor(GRAY)
        c.drawString(2*cm, y, f"NCM: {product.get('ncm_code', 'N/A')}")
        y -= 0.7*cm
        route = product.get("trade_route", {})
        c.drawString(2*cm, y, f"Rota: {route.get('origin_name', 'Brasil')} → {route.get('destination_name', 'Itália')}")
        
        # Risk Score Box
        y -= 2*cm
        score = product.get("risk_score", 50)
        status = product.get("status", "PENDING")
        
        # Score circle (simplified as box)
        c.setFillColor(LIGHT_GREEN)
        c.roundRect(2*cm, y - 1.5*cm, 6*cm, 3*cm, 10, fill=1, stroke=0)
        c.setFillColor(GREEN)
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(5*cm, y - 0.2*cm, str(score))
        c.setFont("Helvetica", 10)
        c.drawCentredString(5*cm, y - 1*cm, "RISK SCORE")
        
        # Status badge
        c.setFillColor(GREEN)
        c.roundRect(9*cm, y - 0.8*cm, 5*cm, 1.5*cm, 8, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(11.5*cm, y - 0.2*cm, status)
        
        # Certificates section
        y -= 4*cm
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, y, "Certificados Necessários")
        y -= 0.3*cm
        c.setStrokeColor(GREEN)
        c.setLineWidth(2)
        c.line(2*cm, y, 8*cm, y)
        
        y -= 0.7*cm
        c.setFont("Helvetica", 10)
        c.setFillColor(GRAY)
        for cert in product.get("certificates_required", []):
            name = cert.get("name", cert) if isinstance(cert, dict) else cert
            issuer = cert.get("issuer", "") if isinstance(cert, dict) else ""
            mandatory = cert.get("mandatory", True) if isinstance(cert, dict) else True
            
            marker = "●" if mandatory else "○"
            text = f"  {name}"
            if issuer:
                text += f" ({issuer})"
            
            c.setFillColor(GREEN if mandatory else GRAY)
            c.drawString(2.2*cm, y, marker)
            c.setFillColor(DARK)
            c.drawString(2.7*cm, y, text)
            y -= 0.55*cm
            
            if y < 3*cm:
                c.showPage()
                y = h - 3*cm
        
        # EU Regulations
        y -= 1*cm
        if y < 6*cm:
            c.showPage()
            y = h - 3*cm
        
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, y, "Regulamentos UE Aplicáveis")
        y -= 0.3*cm
        c.setStrokeColor(GREEN)
        c.line(2*cm, y, 8*cm, y)
        
        y -= 0.7*cm
        c.setFont("Helvetica", 10)
        for reg in product.get("eu_regulations", []):
            code = reg.get("code", reg) if isinstance(reg, dict) else reg
            title = reg.get("title", "") if isinstance(reg, dict) else ""
            
            c.setFillColor(GREEN)
            c.drawString(2.2*cm, y, "§")
            c.setFillColor(DARK)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2.7*cm, y, code)
            if title:
                c.setFont("Helvetica", 9)
                c.setFillColor(GRAY)
                y -= 0.45*cm
                c.drawString(2.7*cm, y, title)
            y -= 0.6*cm
            c.setFont("Helvetica", 10)
            
            if y < 3*cm:
                c.showPage()
                y = h - 3*cm
        
        # Brazilian Requirements
        y -= 1*cm
        if y < 6*cm:
            c.showPage()
            y = h - 3*cm
        
        c.setFillColor(DARK)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(2*cm, y, "Requisitos Brasileiros")
        y -= 0.3*cm
        c.setStrokeColor(GREEN)
        c.line(2*cm, y, 8*cm, y)
        
        y -= 0.7*cm
        c.setFont("Helvetica", 10)
        c.setFillColor(DARK)
        for req in product.get("brazilian_requirements", []):
            text = req if isinstance(req, str) else str(req)
            c.drawString(2.2*cm, y, f"→ {text}")
            y -= 0.55*cm
            if y < 3*cm:
                c.showPage()
                y = h - 3*cm
        
        # MRL Table
        mrl = product.get("max_residue_limits", {})
        if mrl:
            y -= 1*cm
            if y < 6*cm:
                c.showPage()
                y = h - 3*cm
            
            c.setFillColor(DARK)
            c.setFont("Helvetica-Bold", 16)
            c.drawString(2*cm, y, "Limites Máximos de Resíduos (LMR)")
            y -= 0.3*cm
            c.setStrokeColor(GREEN)
            c.line(2*cm, y, 10*cm, y)
            
            y -= 0.7*cm
            c.setFont("Helvetica", 10)
            for substance, info in mrl.items():
                name = substance.replace("_", " ").title()
                limit = info.get("limit", info) if isinstance(info, dict) else str(info)
                reg = info.get("regulation", "") if isinstance(info, dict) else ""
                
                c.setFillColor(DARK)
                c.drawString(2.5*cm, y, f"{name}: {limit}")
                if reg:
                    c.setFillColor(GRAY)
                    c.setFont("Helvetica", 8)
                    c.drawString(12*cm, y, f"({reg})")
                    c.setFont("Helvetica", 10)
                y -= 0.55*cm
                if y < 3*cm:
                    c.showPage()
                    y = h - 3*cm
        
        # Alerts
        alerts = product.get("alerts", [])
        if alerts:
            y -= 1*cm
            if y < 4*cm:
                c.showPage()
                y = h - 3*cm
            
            c.setFillColor(HexColor("#FFF3E0"))
            c.roundRect(1.5*cm, y - len(alerts)*0.6*cm - 0.5*cm, w - 3*cm, len(alerts)*0.6*cm + 1.2*cm, 5, fill=1, stroke=0)
            
            c.setFillColor(DARK)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(2*cm, y, "Alertas")
            y -= 0.6*cm
            c.setFont("Helvetica", 9)
            for alert in alerts:
                text = alert if isinstance(alert, str) else str(alert)
                c.drawString(2.5*cm, y, text[:90])
                y -= 0.5*cm
        
        # Footer
        c.setFillColor(GRAY)
        c.setFont("Helvetica", 7)
        source = product.get("data_source", "unknown")
        source_label = {
            "manus_ai_realtime": "Pesquisa IA em Tempo Real (Manus AI)",
            "dyad_agent_realtime": "Pesquisa IA em Tempo Real (Dyad)",
            "reference_knowledge": "Base de Referência (atualização IA recomendada)",
            "cache": "Cache (dados previamente pesquisados)",
            "template_pending_research": "Template (pesquisa IA pendente)",
        }.get(source, source)
        
        c.drawString(1.5*cm, 1*cm, 
                     f"ZOI Sentinel v4.2 | Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M')} | "
                     f"Fonte: {source_label}")
        c.drawRightString(w - 1.5*cm, 1*cm, "© ZOI Trade Advisory - Confidencial")
        
        c.save()
        return buffer.getvalue()
    
    except ImportError:
        # Fallback mínimo com fpdf2
        try:
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 22)
            pdf.cell(0, 12, "ZOI Sentinel", ln=True)
            pdf.set_font("Helvetica", "", 11)
            pdf.cell(0, 8, "Trade Compliance Report", ln=True)
            pdf.ln(8)
            pdf.set_font("Helvetica", "B", 18)
            pdf.cell(0, 10, product.get("product_name", "Produto"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 7, f"NCM: {product.get('ncm_code', 'N/A')}", ln=True)
            pdf.cell(0, 7, f"Risk Score: {product.get('risk_score', 'N/A')}/100", ln=True)
            pdf.cell(0, 7, f"Status: {product.get('status', 'N/A')}", ln=True)
            pdf.cell(0, 7, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)
            return bytes(pdf.output())
        except ImportError:
            raise HTTPException(status_code=500, detail="PDF generator not available. Install: reportlab")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "service": "ZOI Sentinel v4.2",
        "architecture": "Zero Database",
        "status": "active",
        "endpoints": {
            "products": "/api/products/{product_slug}",
            "export_pdf": "/api/products/{product_slug}/export-pdf",
            "refresh": "/api/products/{product_slug}/refresh",
            "health": "/health",
            "list_products": "/api/products",
        }
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "4.2.0",
        "architecture": "zero_database",
        "ai_services": {
            "manus": "configured" if MANUS_API_KEY else "not_configured",
            "dyad": "configured" if DYAD_API_KEY else "not_configured",
        },
        "cache_size": len(PRODUCT_CACHE),
        "known_products": len(REFERENCE_KNOWLEDGE),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/products")
async def list_products():
    """Lista produtos disponíveis na base de referência."""
    products = []
    for slug, data in REFERENCE_KNOWLEDGE.items():
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
        "note": "Qualquer produto pode ser pesquisado via /api/products/{slug}. "
                "Produtos não listados serão pesquisados via IA em tempo real.",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/products/{product_slug}")
async def get_product(product_slug: str):
    """
    Retorna dados de compliance de um produto.
    ZERO DATABASE: pesquisa IA → cache → knowledge base → template
    NUNCA retorna 404.
    """
    logger.info(f"📦 PRODUCT REQUEST: {product_slug}")
    
    product_data = await get_product_data(product_slug)
    
    return {
        "success": True,
        "product": product_data,
        "architecture": "zero_database_v4",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/products/{product_slug}/export-pdf")
async def export_product_pdf(product_slug: str):
    """
    Gera e retorna PDF de compliance para um produto.
    CORRIGIDO: Não depende de banco de dados.
    """
    logger.info(f"📄 PDF GENERATION REQUEST: {product_slug}")
    
    # Obter dados (NUNCA falha com 404)
    product_data = await get_product_data(product_slug)
    
    try:
        pdf_bytes = generate_compliance_pdf(product_data)
        
        safe_name = product_slug.replace("/", "_").replace("\\", "_")
        filename = f"ZOI_Compliance_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition",
                "X-ZOI-Version": "4.2.0",
            }
        )
    except Exception as e:
        logger.error(f"❌ PDF generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar PDF: {str(e)}")


@app.get("/api/products/{product_slug}/refresh")
async def refresh_product(product_slug: str):
    """
    Força atualização via IA (Manus/Dyad).
    Chamado quando usuário clica 'Atualizar via IA'.
    """
    logger.info(f"🔄 REFRESH REQUEST (force): {product_slug}")
    
    product_data = await get_product_data(product_slug, force_refresh=True)
    
    return {
        "success": True,
        "product": product_data,
        "refreshed": True,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# OPTIONS handler explícito (backup para CORS)
# ============================================================================
@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request, rest_of_path: str):
    """
    Handler explícito para requisições OPTIONS (CORS preflight).
    Isso é um safety net - o CORSMiddleware deveria tratar,
    mas se não tratar, este endpoint garante resposta 200.
    """
    origin = request.headers.get("origin", "")
    
    return JSONResponse(
        content={"status": "ok"},
        headers={
            "Access-Control-Allow-Origin": origin if origin in ALLOWED_ORIGINS else ALLOWED_ORIGINS[0],
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "3600",
            "Access-Control-Allow-Credentials": "true",
        }
    )


# ============================================================================
# STARTUP & SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup():
    logger.info("=" * 70)
    logger.info("🚀 ZOI SENTINEL v4.2 - Zero Database Architecture")
    logger.info(f"📡 Manus AI: {'CONFIGURED' if MANUS_API_KEY else 'NOT CONFIGURED'}")
    logger.info(f"🤖 Dyad Agent: {'CONFIGURED' if DYAD_API_KEY else 'NOT CONFIGURED'}")
    logger.info(f"📦 Reference products: {len(REFERENCE_KNOWLEDGE)}")
    logger.info(f"🌐 CORS origins: {len(ALLOWED_ORIGINS)} configured")
    logger.info("=" * 70)


# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
