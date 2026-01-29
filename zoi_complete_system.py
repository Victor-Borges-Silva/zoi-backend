"""
ZOI Sentinel v4.0 - Zero Database Architecture
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🧠 LIVING INTELLIGENCE SYSTEM
   - Zero Dependency on Static Compliance Tables
   - AI-Driven Real-Time Research (Manus AI / Dyad)
   - 24-Hour Cache Strategy Only
   - Premium PDF Reports (Business Class Design)

📡 DATA SOVEREIGNTY v2.0
   - Manus AI Agent searches MAPA, ANVISA, Siscomex in real-time
   - Database serves ONLY as 24h cache
   - Mandatory fresh search if data > 24 hours old

🎯 TARGET ARCHITECTURE
   - Frontend Request → Check Cache (< 24h?) → If YES: Return
   - If NO: Launch Manus AI → Wait for completion → Save → Return
   - PDF Generation: ALWAYS wait for AI completion

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from io import BytesIO

import requests
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, Text, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas

# ══════════════════════════════════════════════════════════════════════════════
# LOGGING CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ZOI_SENTINEL_V4")

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE CONFIGURATION (24-HOUR CACHE ONLY)
# ══════════════════════════════════════════════════════════════════════════════

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/zoi_db"
).replace("postgres://", "postgresql://")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ══════════════════════════════════════════════════════════════════════════════
# DATABASE MODELS (CACHE ONLY - NO STATIC COMPLIANCE DATA)
# ══════════════════════════════════════════════════════════════════════════════

class Product(Base):
    """Product Master Data (Basic Info Only)"""
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    name_pt = Column(String, nullable=False)
    name_it = Column(String)
    ncm_code = Column(String, nullable=False, index=True)
    direction = Column(String)  # "export" or "import"
    
    # AI Cache (Living Intelligence Data)
    ai_last_check = Column(DateTime, nullable=True)  # Last AI search timestamp
    ai_raw_response = Column(JSON, nullable=True)  # Full AI response
    ai_status = Column(String, nullable=True)  # "green", "yellow", "red"
    ai_score = Column(Float, nullable=True)
    ai_risk_factors = Column(JSON, nullable=True)
    ai_compliance_alerts = Column(JSON, nullable=True)
    ai_technical_specs = Column(JSON, nullable=True)
    ai_barriers = Column(JSON, nullable=True)
    ai_documents_required = Column(JSON, nullable=True)
    ai_estimated_costs = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# ══════════════════════════════════════════════════════════════════════════════
# MANUS AI / DYAD AGENT INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

class ManusAIResearchAgent:
    """
    🤖 MANUS AI RESEARCH AGENT - ZERO DATABASE APPROACH
    
    This agent replaces ALL static compliance tables.
    It performs real-time research on:
    - MAPA (SISCOLE/Vigiagro)
    - ANVISA
    - Siscomex
    
    Returns structured data for immediate use.
    """
    
    def __init__(self):
        # Try Manus AI first, fallback to Dyad
        self.manus_api_key = os.environ.get('MANUS_API_KEY')
        self.manus_api_url = os.environ.get(
            'MANUS_API_URL', 
            'https://api.manus.ai/v1/research'
        )
        
        self.dyad_api_key = os.environ.get('DYAD_API_KEY')
        self.dyad_api_url = os.environ.get(
            'DYAD_API_URL',
            'https://api.dyad.sh/v1/agents/run'
        )
        
        if self.manus_api_key:
            logger.info("✅ Manus AI configured - Using as primary research agent")
            self.use_manus = True
        elif self.dyad_api_key:
            logger.info("✅ Dyad AI configured - Using as research agent")
            self.use_manus = False
        else:
            logger.error("❌ NO AI AGENT CONFIGURED! System cannot operate.")
            raise ValueError("MANUS_API_KEY or DYAD_API_KEY required for v4.0")
    
    def run_deep_search(
        self,
        product_name: str,
        ncm_code: str,
        direction: str,
        origin_country: str = "Brasil",
        destination_country: str = "Itália"
    ) -> Optional[Dict[str, Any]]:
        """
        🔍 DEEP SEARCH - REAL-TIME COMPLIANCE RESEARCH
        
        This method performs live research on Brazilian regulatory portals
        and returns structured compliance intelligence.
        
        Args:
            product_name: Product name in Portuguese
            ncm_code: 8-digit NCM code
            direction: "export" or "import"
            origin_country: Origin (default: Brasil)
            destination_country: Destination (default: Itália)
        
        Returns:
            Structured dict with all compliance data
        """
        
        if not ncm_code or len(ncm_code) != 8:
            logger.error(f"❌ Invalid NCM code: {ncm_code}")
            return None
        
        try:
            logger.info(f"\n{'━'*80}")
            logger.info(f"🔍 DEEP SEARCH INITIATED - ZOI Sentinel v4.0")
            logger.info(f"Product: {product_name}")
            logger.info(f"NCM: {ncm_code}")
            logger.info(f"Direction: {direction}")
            logger.info(f"Route: {origin_country} → {destination_country}")
            logger.info(f"Agent: {'Manus AI' if self.use_manus else 'Dyad AI'}")
            logger.info(f"{'━'*80}\n")
            
            if self.use_manus:
                return self._run_manus_search(
                    product_name, ncm_code, direction,
                    origin_country, destination_country
                )
            else:
                return self._run_dyad_search(
                    product_name, ncm_code, direction,
                    origin_country, destination_country
                )
        
        except Exception as e:
            logger.error(f"❌ Deep Search Failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _run_manus_search(
        self, product_name, ncm_code, direction, origin, destination
    ) -> Optional[Dict]:
        """Execute Manus AI research"""
        
        prompt = f"""
# TAREFA: Pesquisa de Compliance para Exportação Brasil → Itália

## PRODUTO
- Nome: {product_name}
- NCM: {ncm_code}
- Origem: {origin}
- Destino: {destination}
- Direção: {direction}

## PORTAIS OBRIGATÓRIOS PARA CONSULTA
1. **MAPA (Ministério da Agricultura)**
   - SISCOLE (Sistema de Controle de Exportação)
   - Vigiagro (Vigilância Agropecuária)
   - URL: https://sistemasweb.agricultura.gov.br/
   
2. **ANVISA (Agência Nacional de Vigilância Sanitária)**
   - Regularização de Alimentos
   - URL: https://www.gov.br/anvisa/
   
3. **Siscomex (Sistema Integrado de Comércio Exterior)**
   - Documentação de exportação
   - URL: https://www.gov.br/siscomex/

## ESTRUTURA DE RESPOSTA OBRIGATÓRIA (JSON)

```json
{{
  "status": "green|yellow|red",
  "score": 0-100,
  "risk_factors": [
    "Lista de fatores de risco identificados"
  ],
  "compliance_alerts": [
    "Alertas regulatórios específicos"
  ],
  "technical_specs": [
    "Especificações técnicas e LMRs"
  ],
  "barriers": {{
    "sanitary": ["Barreiras sanitárias específicas"],
    "phytosanitary": ["Barreiras fitossanitárias"],
    "documentary": ["Documentos obrigatórios"]
  }},
  "documents_required": [
    {{
      "name": "Nome do documento",
      "issuer": "Órgão emissor",
      "validity": "Prazo de validade"
    }}
  ],
  "estimated_costs": {{
    "certifications": "R$ XXX",
    "inspections": "R$ XXX",
    "documentation": "R$ XXX",
    "total_landing_cost_estimate": "R$ XXX"
  }},
  "sources": ["URLs consultadas"],
  "last_updated": "ISO 8601 timestamp"
}}
```

IMPORTANTE: Retorne APENAS o JSON, sem texto adicional.
"""
        
        payload = {
            "query": prompt,
            "sources": [
                "https://sistemasweb.agricultura.gov.br/",
                "https://www.gov.br/anvisa/",
                "https://www.gov.br/siscomex/"
            ],
            "max_tokens": 4000,
            "temperature": 0.3
        }
        
        headers = {
            "Authorization": f"Bearer {self.manus_api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info("📡 Sending request to Manus AI...")
        start_time = datetime.now()
        
        response = requests.post(
            self.manus_api_url,
            json=payload,
            headers=headers,
            timeout=120
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"⏱️ Manus AI response time: {elapsed:.1f}s")
        
        if response.status_code != 200:
            logger.error(f"❌ Manus AI error: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return None
        
        data = response.json()
        
        # Extract JSON from response
        result_text = data.get('result', data.get('response', ''))
        
        # Try to extract JSON
        try:
            # Remove markdown code blocks if present
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            parsed = json.loads(result_text.strip())
            logger.info("✅ Manus AI research completed successfully")
            return parsed
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse Manus AI JSON: {e}")
            logger.error(f"Raw response: {result_text[:500]}")
            return None
    
    def _run_dyad_search(
        self, product_name, ncm_code, direction, origin, destination
    ) -> Optional[Dict]:
        """Execute Dyad AI research (fallback)"""
        
        prompt = f"""
Você é o agente de pesquisa de compliance do ZOI Sentinel v4.0.

PRODUTO: {product_name}
NCM: {ncm_code}
ROTA: {origin} → {destination}
DIREÇÃO: {direction}

PORTAIS A CONSULTAR:
1. MAPA/SISCOLE/Vigiagro
2. ANVISA
3. Siscomex

Retorne um JSON com:
- status (green/yellow/red)
- score (0-100)
- risk_factors (lista)
- compliance_alerts (lista)
- technical_specs (lista)
- barriers (objeto com sanitary, phytosanitary, documentary)
- documents_required (lista de objetos)
- estimated_costs (objeto com certifications, inspections, documentation, total_landing_cost_estimate)
- sources (URLs consultadas)
- last_updated (timestamp)

RETORNE APENAS O JSON, sem texto adicional.
"""
        
        payload = {
            "prompt": prompt,
            "max_tokens": 4000,
            "temperature": 0.3
        }
        
        headers = {
            "Authorization": f"Bearer {self.dyad_api_key}",
            "Content-Type": "application/json"
        }
        
        logger.info("📡 Sending request to Dyad AI...")
        start_time = datetime.now()
        
        response = requests.post(
            self.dyad_api_url,
            json=payload,
            headers=headers,
            timeout=120
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"⏱️ Dyad AI response time: {elapsed:.1f}s")
        
        if response.status_code != 200:
            logger.error(f"❌ Dyad AI error: {response.status_code}")
            return None
        
        data = response.json()
        result_text = data.get('result', data.get('response', ''))
        
        try:
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0]
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0]
            
            parsed = json.loads(result_text.strip())
            logger.info("✅ Dyad AI research completed successfully")
            return parsed
        
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse Dyad AI JSON: {e}")
            return None

# ══════════════════════════════════════════════════════════════════════════════
# CACHE MANAGER (24-HOUR STRATEGY)
# ══════════════════════════════════════════════════════════════════════════════

class CacheManager:
    """
    ⏰ 24-HOUR CACHE STRATEGY
    
    Database serves ONLY as a 24-hour cache.
    If data is older than 24 hours, MUST trigger new AI search.
    """
    
    @staticmethod
    def is_cache_valid(product: Product) -> bool:
        """Check if cached AI data is still valid (< 24 hours)"""
        
        if not product.ai_last_check:
            logger.info(f"❌ No cached data for {product.key}")
            return False
        
        age = datetime.utcnow() - product.ai_last_check
        valid = age < timedelta(hours=24)
        
        if valid:
            logger.info(f"✅ Cache valid for {product.key} (age: {age.total_seconds()/3600:.1f}h)")
        else:
            logger.info(f"⏰ Cache expired for {product.key} (age: {age.total_seconds()/3600:.1f}h)")
        
        return valid
    
    @staticmethod
    def save_ai_results(product: Product, ai_data: Dict, db) -> None:
        """Save AI research results to cache"""
        
        try:
            product.ai_last_check = datetime.utcnow()
            product.ai_raw_response = ai_data
            product.ai_status = ai_data.get('status', 'yellow')
            product.ai_score = ai_data.get('score', 50.0)
            product.ai_risk_factors = ai_data.get('risk_factors', [])
            product.ai_compliance_alerts = ai_data.get('compliance_alerts', [])
            product.ai_technical_specs = ai_data.get('technical_specs', [])
            product.ai_barriers = ai_data.get('barriers', {})
            product.ai_documents_required = ai_data.get('documents_required', [])
            product.ai_estimated_costs = ai_data.get('estimated_costs', {})
            
            db.commit()
            logger.info(f"💾 AI results cached for {product.key}")
        
        except Exception as e:
            logger.error(f"❌ Failed to save cache: {e}")
            db.rollback()

# ══════════════════════════════════════════════════════════════════════════════
# PDF GENERATOR - BUSINESS CLASS DESIGN
# ══════════════════════════════════════════════════════════════════════════════

class BusinessClassPDFGenerator:
    """
    📄 PREMIUM PDF REPORT GENERATOR
    
    Business-class design with:
    - Professional header
    - Real-time verification seal
    - Clean tables and sections
    - Executive summary format
    """
    
    def __init__(self):
        self.pagesize = A4
        self.width, self.height = self.pagesize
    
    def _add_header(self, canvas_obj, doc):
        """Add professional header to each page"""
        canvas_obj.saveState()
        
        # Header background
        canvas_obj.setFillColorRGB(0.1, 0.2, 0.35)  # Dark blue
        canvas_obj.rect(0, self.height - 2*cm, self.width, 2*cm, fill=True, stroke=False)
        
        # ZOI Logo text
        canvas_obj.setFillColorRGB(1, 1, 1)  # White
        canvas_obj.setFont("Helvetica-Bold", 20)
        canvas_obj.drawString(2*cm, self.height - 1.3*cm, "ZOI")
        
        canvas_obj.setFont("Helvetica", 10)
        canvas_obj.drawString(2*cm, self.height - 1.7*cm, "Strategic Advisory")
        
        # Document title
        canvas_obj.setFont("Helvetica-Bold", 14)
        canvas_obj.drawRightString(
            self.width - 2*cm,
            self.height - 1.5*cm,
            "Dossier de Inteligência de Mercado"
        )
        
        canvas_obj.restoreState()
    
    def _add_footer(self, canvas_obj, doc):
        """Add footer with page numbers"""
        canvas_obj.saveState()
        
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColorRGB(0.5, 0.5, 0.5)
        
        footer_text = f"ZOI Sentinel © {datetime.now().year} | Página {doc.page}"
        canvas_obj.drawCentredString(
            self.width / 2,
            1*cm,
            footer_text
        )
        
        canvas_obj.restoreState()
    
    def generate_dossier(
        self,
        product_data: Dict,
        ai_data: Dict,
        verification_time: datetime
    ) -> BytesIO:
        """
        Generate premium PDF dossier
        
        Args:
            product_data: Product information
            ai_data: AI research results
            verification_time: Timestamp of AI verification
        
        Returns:
            BytesIO buffer with PDF
        """
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.pagesize,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=3*cm,
            bottomMargin=2.5*cm
        )
        
        # Story (PDF content)
        story = []
        
        # Styles
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a3352'),
            spaceAfter=30,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a3352'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold'
        )
        
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['BodyText'],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY
        )
        
        # ═══════════════════════════════════════════════════════════════
        # COVER PAGE
        # ═══════════════════════════════════════════════════════════════
        
        # Title
        story.append(Spacer(1, 1*cm))
        story.append(Paragraph(
            "Dossier de Inteligência de Mercado",
            title_style
        ))
        
        # Verification Seal
        seal_style = ParagraphStyle(
            'Seal',
            parent=body_style,
            fontSize=11,
            textColor=colors.HexColor('#d97706'),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        verification_text = f"""
        ⚠️ VERIFICADO EM TEMPO REAL VIA AGENTE IA<br/>
        {verification_time.strftime('%d/%m/%Y às %H:%M:%S')} UTC
        """
        
        story.append(Spacer(1, 0.5*cm))
        story.append(Paragraph(verification_text, seal_style))
        story.append(Spacer(1, 1*cm))
        
        # Product Information Box
        product_info_data = [
            ['PRODUTO', product_data.get('name_pt', 'N/A')],
            ['NOME ITALIANO', product_data.get('name_it', 'N/A')],
            ['CÓDIGO NCM', product_data.get('ncm_code', 'N/A')],
            ['DIREÇÃO', product_data.get('direction', 'N/A').upper()],
        ]
        
        product_table = Table(product_info_data, colWidths=[6*cm, 10*cm])
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#1a3352')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('BACKGROUND', (1, 0), (1, -1), colors.HexColor('#f3f4f6')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('PADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        story.append(product_table)
        story.append(Spacer(1, 1*cm))
        
        # Risk Score (Big Number)
        score = ai_data.get('score', 50)
        status = ai_data.get('status', 'yellow')
        
        status_colors = {
            'green': colors.HexColor('#10b981'),
            'yellow': colors.HexColor('#f59e0b'),
            'red': colors.HexColor('#ef4444')
        }
        
        score_style = ParagraphStyle(
            'Score',
            parent=body_style,
            fontSize=48,
            textColor=status_colors.get(status, colors.grey),
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        story.append(Paragraph(f"{score:.1f}", score_style))
        
        score_label_style = ParagraphStyle(
            'ScoreLabel',
            parent=body_style,
            fontSize=12,
            alignment=TA_CENTER,
            textColor=colors.grey
        )
        
        status_labels = {
            'green': 'BAIXO RISCO',
            'yellow': 'RISCO MODERADO',
            'red': 'ALTO RISCO'
        }
        
        story.append(Paragraph(
            status_labels.get(status, 'RISCO MODERADO'),
            score_label_style
        ))
        
        story.append(PageBreak())
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 1: FATORES DE RISCO
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("1. Fatores de Risco Identificados", heading_style))
        story.append(Spacer(1, 0.3*cm))
        
        risk_factors = ai_data.get('risk_factors', [])
        
        if risk_factors:
            for i, factor in enumerate(risk_factors, 1):
                story.append(Paragraph(f"• {factor}", body_style))
                story.append(Spacer(1, 0.2*cm))
        else:
            story.append(Paragraph(
                "Nenhum fator de risco crítico identificado.",
                body_style
            ))
        
        story.append(Spacer(1, 0.5*cm))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 2: BARREIRAS SANITÁRIAS E FITOSSANITÁRIAS
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("2. Barreiras Sanitárias e Fitossanitárias", heading_style))
        story.append(Spacer(1, 0.3*cm))
        
        barriers = ai_data.get('barriers', {})
        
        # Sanitary Barriers
        if barriers.get('sanitary'):
            story.append(Paragraph("<b>Barreiras Sanitárias:</b>", body_style))
            for barrier in barriers['sanitary']:
                story.append(Paragraph(f"• {barrier}", body_style))
            story.append(Spacer(1, 0.3*cm))
        
        # Phytosanitary Barriers
        if barriers.get('phytosanitary'):
            story.append(Paragraph("<b>Barreiras Fitossanitárias:</b>", body_style))
            for barrier in barriers['phytosanitary']:
                story.append(Paragraph(f"• {barrier}", body_style))
            story.append(Spacer(1, 0.3*cm))
        
        # Documentary Requirements
        if barriers.get('documentary'):
            story.append(Paragraph("<b>Requisitos Documentais:</b>", body_style))
            for req in barriers['documentary']:
                story.append(Paragraph(f"• {req}", body_style))
            story.append(Spacer(1, 0.3*cm))
        
        story.append(Spacer(1, 0.5*cm))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 3: DOCUMENTAÇÃO OBRIGATÓRIA
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("3. Documentação Obrigatória", heading_style))
        story.append(Spacer(1, 0.3*cm))
        
        documents = ai_data.get('documents_required', [])
        
        if documents:
            doc_data = [['Documento', 'Órgão Emissor', 'Validade']]
            
            for doc in documents:
                doc_data.append([
                    doc.get('name', 'N/A'),
                    doc.get('issuer', 'N/A'),
                    doc.get('validity', 'N/A')
                ])
            
            doc_table = Table(doc_data, colWidths=[6*cm, 6*cm, 4*cm])
            doc_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3352')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f9fafb')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('PADDING', (0, 0), (-1, -1), 8),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(doc_table)
        else:
            story.append(Paragraph(
                "Informação não disponível no momento.",
                body_style
            ))
        
        story.append(Spacer(1, 0.5*cm))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 4: CUSTOS ESTIMADOS (LANDING COST)
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("4. Custos Estimados (Landing Cost)", heading_style))
        story.append(Spacer(1, 0.3*cm))
        
        costs = ai_data.get('estimated_costs', {})
        
        if costs:
            cost_data = [['Item', 'Valor Estimado']]
            
            cost_items = {
                'certifications': 'Certificações',
                'inspections': 'Inspeções',
                'documentation': 'Documentação',
                'total_landing_cost_estimate': 'TOTAL ESTIMADO'
            }
            
            for key, label in cost_items.items():
                value = costs.get(key, 'N/A')
                if key == 'total_landing_cost_estimate':
                    cost_data.append([f"<b>{label}</b>", f"<b>{value}</b>"])
                else:
                    cost_data.append([label, value])
            
            cost_table = Table(cost_data, colWidths=[10*cm, 6*cm])
            cost_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a3352')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 1), (-1, -2), colors.HexColor('#f9fafb')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fef3c7')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('PADDING', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            story.append(cost_table)
        else:
            story.append(Paragraph(
                "Estimativa de custos não disponível.",
                body_style
            ))
        
        story.append(Spacer(1, 0.5*cm))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 5: ALERTAS DE COMPLIANCE
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("5. Alertas de Compliance", heading_style))
        story.append(Spacer(1, 0.3*cm))
        
        alerts = ai_data.get('compliance_alerts', [])
        
        if alerts:
            for alert in alerts:
                story.append(Paragraph(f"⚠️ {alert}", body_style))
                story.append(Spacer(1, 0.2*cm))
        else:
            story.append(Paragraph(
                "Nenhum alerta crítico no momento.",
                body_style
            ))
        
        story.append(Spacer(1, 0.5*cm))
        
        # ═══════════════════════════════════════════════════════════════
        # SECTION 6: ESPECIFICAÇÕES TÉCNICAS
        # ═══════════════════════════════════════════════════════════════
        
        story.append(Paragraph("6. Especificações Técnicas", heading_style))
        story.append(Spacer(1, 0.3*cm))
        
        specs = ai_data.get('technical_specs', [])
        
        if specs:
            for spec in specs:
                story.append(Paragraph(f"• {spec}", body_style))
                story.append(Spacer(1, 0.2*cm))
        else:
            story.append(Paragraph(
                "Especificações técnicas não disponíveis.",
                body_style
            ))
        
        # ═══════════════════════════════════════════════════════════════
        # FOOTER / DISCLAIMER
        # ═══════════════════════════════════════════════════════════════
        
        story.append(PageBreak())
        
        disclaimer_style = ParagraphStyle(
            'Disclaimer',
            parent=body_style,
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_JUSTIFY
        )
        
        disclaimer_text = f"""
        <b>AVISO LEGAL</b><br/><br/>
        Este dossier foi gerado em {verification_time.strftime('%d/%m/%Y às %H:%M:%S')} UTC 
        por meio de pesquisa em tempo real realizada por Agente de Inteligência Artificial nos 
        principais portais regulatórios brasileiros (MAPA, ANVISA, Siscomex).<br/><br/>
        
        As informações aqui contidas refletem o estado regulatório vigente no momento da consulta 
        e devem ser utilizadas como referência estratégica. Recomenda-se verificação adicional 
        junto aos órgãos competentes antes de decisões comerciais definitivas.<br/><br/>
        
        <b>ZOI Strategic Advisory</b> | Sistema ZOI Sentinel v4.0 - Living Intelligence Architecture
        """
        
        story.append(Paragraph(disclaimer_text, disclaimer_style))
        
        # Build PDF
        doc.build(
            story,
            onFirstPage=self._add_header,
            onLaterPages=self._add_header
        )
        
        buffer.seek(0)
        return buffer

# ══════════════════════════════════════════════════════════════════════════════
# FASTAPI APPLICATION
# ══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="ZOI Sentinel v4.0",
    description="Living Intelligence System - Zero Database Architecture",
    version="4.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize AI Agent
try:
    ai_agent = ManusAIResearchAgent()
except ValueError as e:
    logger.error(f"Failed to initialize AI agent: {e}")
    ai_agent = None

# ══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    """System status"""
    return {
        "service": "ZOI Sentinel",
        "version": "4.0.0",
        "architecture": "Zero Database - Living Intelligence",
        "status": "operational",
        "ai_agent": "Manus AI" if ai_agent and ai_agent.use_manus else "Dyad AI",
        "cache_strategy": "24 hours",
        "features": [
            "🧠 Real-Time AI Research",
            "📡 Zero Static Compliance Tables",
            "🎯 24-Hour Cache Only",
            "📄 Business Class PDF Reports",
            "⚡ Async/Await PDF Generation"
        ]
    }

@app.get("/api/products/{product_key}")
def get_product_intelligence(product_key: str, db: SessionLocal = Depends(get_db)):
    """
    Get product compliance intelligence
    
    LOGIC:
    1. Check cache (< 24h)
    2. If valid: Return cached data
    3. If invalid: Launch AI research → Wait → Save → Return
    """
    
    logger.info(f"\n{'━'*80}")
    logger.info(f"🔍 PRODUCT INTELLIGENCE REQUEST: {product_key}")
    logger.info(f"{'━'*80}")
    
    # Find product
    product = db.query(Product).filter(Product.key == product_key).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check cache validity
    cache_valid = CacheManager.is_cache_valid(product)
    
    if cache_valid:
        logger.info("✅ Returning cached data")
        
        return {
            "product": {
                "key": product.key,
                "name_pt": product.name_pt,
                "name_it": product.name_it,
                "ncm_code": product.ncm_code,
                "direction": product.direction
            },
            "intelligence": {
                "status": product.ai_status,
                "score": product.ai_score,
                "risk_factors": product.ai_risk_factors or [],
                "compliance_alerts": product.ai_compliance_alerts or [],
                "technical_specs": product.ai_technical_specs or [],
                "barriers": product.ai_barriers or {},
                "documents_required": product.ai_documents_required or [],
                "estimated_costs": product.ai_estimated_costs or {},
                "data_source": "cache",
                "last_updated": product.ai_last_check.isoformat() if product.ai_last_check else None,
                "cache_age_hours": (
                    (datetime.utcnow() - product.ai_last_check).total_seconds() / 3600
                    if product.ai_last_check else None
                )
            }
        }
    
    # Cache expired or no data - Launch AI research
    logger.info("🚀 Launching real-time AI research...")
    
    if not ai_agent:
        raise HTTPException(
            status_code=503,
            detail="AI Agent not configured"
        )
    
    ai_data = ai_agent.run_deep_search(
        product_name=product.name_pt,
        ncm_code=product.ncm_code,
        direction=product.direction or "export",
        origin_country="Brasil",
        destination_country="Itália"
    )
    
    if not ai_data:
        raise HTTPException(
            status_code=500,
            detail="AI research failed"
        )
    
    # Save to cache
    CacheManager.save_ai_results(product, ai_data, db)
    
    logger.info("✅ Fresh AI intelligence returned")
    
    return {
        "product": {
            "key": product.key,
            "name_pt": product.name_pt,
            "name_it": product.name_it,
            "ncm_code": product.ncm_code,
            "direction": product.direction
        },
        "intelligence": {
            "status": ai_data.get('status'),
            "score": ai_data.get('score'),
            "risk_factors": ai_data.get('risk_factors', []),
            "compliance_alerts": ai_data.get('compliance_alerts', []),
            "technical_specs": ai_data.get('technical_specs', []),
            "barriers": ai_data.get('barriers', {}),
            "documents_required": ai_data.get('documents_required', []),
            "estimated_costs": ai_data.get('estimated_costs', {}),
            "data_source": "live_ai",
            "last_updated": datetime.utcnow().isoformat(),
            "cache_age_hours": 0
        }
    }

@app.get("/api/products/{product_key}/export-pdf")
async def export_business_class_pdf(product_key: str, db: SessionLocal = Depends(get_db)):
    """
    Generate Business Class PDF Report
    
    CRITICAL: This endpoint ALWAYS waits for AI completion
    to ensure the PDF contains real-time verified data.
    """
    
    logger.info(f"\n{'━'*80}")
    logger.info(f"📄 PDF GENERATION REQUEST: {product_key}")
    logger.info(f"{'━'*80}")
    
    # Find product
    product = db.query(Product).filter(Product.key == product_key).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Check cache validity
    cache_valid = CacheManager.is_cache_valid(product)
    
    ai_data = None
    verification_time = datetime.utcnow()
    
    if not cache_valid:
        logger.info("⏳ Cache invalid - Launching AI research for PDF...")
        
        if not ai_agent:
            raise HTTPException(
                status_code=503,
                detail="AI Agent not configured"
            )
        
        # CRITICAL: Wait for AI completion
        ai_data = ai_agent.run_deep_search(
            product_name=product.name_pt,
            ncm_code=product.ncm_code,
            direction=product.direction or "export",
            origin_country="Brasil",
            destination_country="Itália"
        )
        
        if not ai_data:
            raise HTTPException(
                status_code=500,
                detail="AI research failed - cannot generate PDF"
            )
        
        # Save fresh data
        CacheManager.save_ai_results(product, ai_data, db)
        
        logger.info("✅ Fresh AI data acquired for PDF")
    
    else:
        logger.info("✅ Using valid cached data for PDF")
        
        # Use cached data
        ai_data = {
            'status': product.ai_status,
            'score': product.ai_score,
            'risk_factors': product.ai_risk_factors or [],
            'compliance_alerts': product.ai_compliance_alerts or [],
            'technical_specs': product.ai_technical_specs or [],
            'barriers': product.ai_barriers or {},
            'documents_required': product.ai_documents_required or [],
            'estimated_costs': product.ai_estimated_costs or {}
        }
        
        verification_time = product.ai_last_check or datetime.utcnow()
    
    # Generate Business Class PDF
    logger.info("📄 Generating Business Class PDF...")
    
    pdf_gen = BusinessClassPDFGenerator()
    
    product_data = {
        'name_pt': product.name_pt,
        'name_it': product.name_it,
        'ncm_code': product.ncm_code,
        'direction': product.direction
    }
    
    pdf_buffer = pdf_gen.generate_dossier(
        product_data=product_data,
        ai_data=ai_data,
        verification_time=verification_time
    )
    
    logger.info("✅ Business Class PDF generated successfully")
    logger.info(f"{'━'*80}\n")
    
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=zoi_dossier_{product_key}.pdf"
        }
    )

@app.post("/api/products/{product_key}/refresh")
def force_ai_refresh(product_key: str, db: SessionLocal = Depends(get_db)):
    """
    Force AI research refresh (ignore cache)
    """
    
    logger.info(f"🔄 Force refresh requested for {product_key}")
    
    product = db.query(Product).filter(Product.key == product_key).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    if not ai_agent:
        raise HTTPException(status_code=503, detail="AI Agent not configured")
    
    ai_data = ai_agent.run_deep_search(
        product_name=product.name_pt,
        ncm_code=product.ncm_code,
        direction=product.direction or "export"
    )
    
    if not ai_data:
        raise HTTPException(status_code=500, detail="AI research failed")
    
    CacheManager.save_ai_results(product, ai_data, db)
    
    return {
        "message": "AI research completed successfully",
        "product_key": product_key,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/products")
def list_products(db: SessionLocal = Depends(get_db)):
    """List all products"""
    products = db.query(Product).all()
    
    return {
        "products": [
            {
                "key": p.key,
                "name_pt": p.name_pt,
                "ncm_code": p.ncm_code,
                "direction": p.direction,
                "cache_valid": CacheManager.is_cache_valid(p),
                "last_check": p.ai_last_check.isoformat() if p.ai_last_check else None
            }
            for p in products
        ]
    }

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    
    logger.info(f"\n{'━'*80}")
    logger.info(f"🚀 ZOI SENTINEL v4.0 - LIVING INTELLIGENCE SYSTEM")
    logger.info(f"{'━'*80}")
    logger.info(f"🔌 Port: {port}")
    logger.info(f"🧠 AI Agent: {'Manus AI' if ai_agent and ai_agent.use_manus else 'Dyad AI'}")
    logger.info(f"💾 Cache Strategy: 24 hours")
    logger.info(f"📄 PDF Design: Business Class")
    logger.info(f"{'━'*80}\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
