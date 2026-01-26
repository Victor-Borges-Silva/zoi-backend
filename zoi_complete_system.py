"""
ZOI Trade Advisory - Complete Production System with Dyad AI Integration
Version 2.1 - Commercial Phase with Real-Time AI Compliance Analysis
"""

import re
import os
import json
import time
import enum
import smtplib
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext

# ==================================================================================
# DYAD AI COMPLIANCE NAVIGATOR - CÉREBRO DO SISTEMA ZOI
# ==================================================================================

class DyadComplianceNavigator:
    """
    Classe que integra a API da Dyad para navegação inteligente e análise de compliance.
    Esta é a ponte entre o Backend (músculos) e a IA (cérebro) do sistema.
    """
    
    def __init__(self):
        self.api_key = os.environ.get('DYAD_API_KEY')
        self.api_url = os.environ.get('DYAD_API_URL', 'https://api.dyad.sh/v1/agents/run')
        
        if not self.api_key:
            print("⚠️ AVISO: DYAD_API_KEY não configurada! Sistema funcionará com dados estáticos.")
        else:
            print(f"✅ Dyad API inicializada: {self.api_url}")
    
    def search_compliance_data(self, ncm_code: str, product_name: str, target_market: str = "EU") -> Optional[Dict[str, Any]]:
        """
        Dispara uma busca via IA na Dyad para encontrar dados de compliance atualizados.
        
        Args:
            ncm_code: Código NCM do produto (ex: "08055000")
            product_name: Nome do produto em português (ex: "Limão Tahiti")
            target_market: Mercado de destino (default: "EU")
        
        Returns:
            Dict com dados de compliance ou None em caso de erro
        """
        
        if not self.api_key:
            print("⚠️ Dyad API não configurada, pulando busca inteligente")
            return None
        
        try:
            print(f"\n{'='*80}")
            print(f"🧠 DYAD AI - Iniciando busca inteligente para: {product_name} (NCM: {ncm_code})")
            print(f"{'='*80}")
            
            # Construção do prompt otimizado para análise de compliance
            prompt = f"""
Você é um especialista em comércio internacional e compliance regulatório.

PRODUTO: {product_name}
NCM: {ncm_code}
MERCADO DESTINO: {target_market}

TAREFA:
Busque e compile as informações mais recentes sobre requisitos de exportação deste produto do Brasil para a União Europeia.

INFORMAÇÕES NECESSÁRIAS:
1. **Limites Máximos de Resíduos (LMR)**: Principais substâncias controladas e seus limites em mg/kg
2. **Alertas RASFF**: Número de alertas sanitários nos últimos 6 e 12 meses
3. **Certificações Obrigatórias**: Quais certificados são necessários (fitossanitário, sanitário, origem)
4. **Barreiras Não-Tarifárias**: Principais restrições e requisitos adicionais
5. **Histórico de Rejeições**: Casos recentes de rejeição de produtos similares

FORMATO DE RESPOSTA:
Retorne APENAS um JSON válido com a estrutura:
{{
  "lmr_data": [
    {{"substance": "Nome da Substância", "eu_limit_mg_kg": 0.0, "source": "Regulamento EU"}}
  ],
  "rasff_alerts": {{
    "last_6_months": 0,
    "last_12_months": 0,
    "common_issues": ["lista", "de", "problemas"]
  }},
  "certifications": {{
    "phytosanitary": true/false,
    "health": true/false,
    "origin": true/false,
    "additional": ["outros", "certificados"]
  }},
  "barriers": ["lista", "de", "barreiras"],
  "recent_rejections": 0,
  "risk_factors": ["fatores", "de", "risco"],
  "recommendations": ["recomendações", "práticas"]
}}

IMPORTANTE: Retorne APENAS o JSON, sem texto adicional antes ou depois.
"""
            
            # Payload para a API da Dyad
            payload = {
                "instructions": prompt,
                "max_steps": 10,
                "timeout_seconds": 120
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            print(f"📡 Enviando requisição para Dyad API...")
            start_time = time.time()
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=130
            )
            
            elapsed_time = time.time() - start_time
            print(f"⏱️ Tempo de resposta: {elapsed_time:.2f}s")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Resposta recebida da Dyad API")
                
                # Extrair o conteúdo da resposta
                output_text = result.get('output', '')
                
                # Tentar extrair JSON da resposta
                compliance_data = self._extract_json_from_response(output_text)
                
                if compliance_data:
                    print(f"✅ Dados de compliance parseados com sucesso")
                    print(f"📊 Alertas RASFF encontrados: {compliance_data.get('rasff_alerts', {}).get('last_12_months', 0)}")
                    print(f"🧪 Substâncias LMR encontradas: {len(compliance_data.get('lmr_data', []))}")
                    return compliance_data
                else:
                    print(f"⚠️ Não foi possível parsear JSON da resposta")
                    print(f"📄 Resposta bruta: {output_text[:500]}...")
                    return None
                    
            else:
                print(f"❌ Erro na API Dyad: Status {response.status_code}")
                print(f"📄 Resposta: {response.text[:500]}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout na requisição para Dyad API (>130s)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Erro de conexão com Dyad API: {e}")
            return None
        except Exception as e:
            print(f"❌ Erro inesperado na busca Dyad: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_json_from_response(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extrai e parseia JSON da resposta da Dyad, mesmo se vier com texto adicional.
        """
        try:
            # Tentar parsear diretamente
            return json.loads(text)
        except json.JSONDecodeError:
            # Tentar encontrar JSON dentro do texto
            import re
            json_pattern = r'\{(?:[^{}]|(?:\{(?:[^{}]|(?:\{[^{}]*\}))*\}))*\}'
            matches = re.findall(json_pattern, text, re.DOTALL)
            
            for match in matches:
                try:
                    parsed = json.loads(match)
                    # Validar se tem a estrutura esperada
                    if 'lmr_data' in parsed or 'rasff_alerts' in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            return None

# ==================================================================================
# MODELOS E CONFIGURAÇÃO DO BANCO DE DADOS
# ==================================================================================

Base = declarative_base()


class TradeDirectionDB(enum.Enum):
    EXPORT = "export"
    IMPORT = "import"


class ProductStateDB(str, enum.Enum):
    ambient = "ambient"
    frozen = "frozen"
    chilled = "chilled"


class RiskStatusDB(enum.Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class Product(Base):
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    name_pt = Column(String(200), nullable=False)
    name_it = Column(String(200), nullable=False)
    name_en = Column(String(200))
    
    ncm_code = Column(String(8), nullable=False)
    hs_code = Column(String(6), nullable=False)
    taric_code = Column(String(10))
    
    direction = Column(SQLEnum(TradeDirectionDB), nullable=False)
    state = Column(SQLEnum(ProductStateDB), nullable=False)
    category = Column(String(50))
    
    shelf_life_days = Column(Integer)
    transport_days_avg = Column(Integer)
    temperature_min_c = Column(Float)
    temperature_max_c = Column(Float)
    
    requires_phytosanitary_cert = Column(Boolean, default=True)
    requires_health_cert = Column(Boolean, default=False)
    requires_origin_cert = Column(Boolean, default=True)
    
    critical_substances = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    risk_assessments = relationship("RiskAssessment", back_populates="product")
    lmr_data = relationship("LMRData", back_populates="product")


class LMRData(Base):
    __tablename__ = 'lmr_data'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    
    substance = Column(String(200), nullable=False)
    source_lmr = Column(Float)
    dest_lmr = Column(Float)
    detection_rate = Column(Float)
    
    source_authority = Column(String(50))
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="lmr_data")


class RiskAssessment(Base):
    __tablename__ = 'risk_assessments'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    
    final_score = Column(Float, nullable=False)
    status = Column(SQLEnum(RiskStatusDB), nullable=False)
    
    rasff_score = Column(Float)
    lmr_score = Column(Float)
    phyto_score = Column(Float)
    logistic_score = Column(Float)
    penalty = Column(Float)
    
    rasff_alerts_6m = Column(Integer, default=0)
    rasff_alerts_12m = Column(Integer, default=0)
    
    recommendations = Column(JSON)
    calculation_timestamp = Column(DateTime, default=datetime.utcnow)
    
    product = relationship("Product", back_populates="risk_assessments")


class NotificationLog(Base):
    __tablename__ = 'notification_logs'
    
    id = Column(Integer, primary_key=True)
    user_email = Column(String(200), nullable=False)
    product_key = Column(String(100), nullable=False)
    risk_score = Column(Float)
    notification_type = Column(String(50))
    sent_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(String(500))


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(200))
    company = Column(String(200))
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    notification_threshold = Column(Float, default=65.0)
    email_notifications = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# Configuração do banco de dados com pool_pre_ping para estabilidade no Render
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://zoi_user:IN3LI5N6OshhlVIDetxmCXhX01es3nK8@dpg-d5pkoeer433s73ddm970-a/zoi_db")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,  # Previne conexões perdidas no Render
    pool_recycle=3600,   # Recicla conexões a cada hora
    pool_size=5,         # Tamanho do pool
    max_overflow=10      # Máximo de conexões extras
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ==================================================================================
# PERFIS DE RISCO NCM - Dados Estáticos como Fallback
# ==================================================================================

NCM_RISK_PROFILES = {
    "08055000": {
        "name": "Limão/Lima",
        "eu_barriers": "high",
        "common_issues": ["LMR Carbendazim", "Mosca das frutas", "Certificação fitossanitária"],
        "historical_rejections": 12,
        "sanitario_base": 75.0,
        "fitossanitario_base": 68.0,
        "logistico_base": 85.0,
        "documental_base": 72.0
    },
    "12019000": {
        "name": "Soja em Grãos",
        "eu_barriers": "medium",
        "common_issues": ["Glifosato LMR", "OGM detection", "Deforestation compliance"],
        "historical_rejections": 5,
        "sanitario_base": 88.0,
        "fitossanitario_base": 82.0,
        "logistico_base": 92.0,
        "documental_base": 85.0
    },
    "09011110": {
        "name": "Café Cru",
        "eu_barriers": "low",
        "common_issues": ["Ochratoxin A", "Origem sustentável"],
        "historical_rejections": 2,
        "sanitario_base": 92.0,
        "fitossanitario_base": 90.0,
        "logistico_base": 88.0,
        "documental_base": 95.0
    },
    "02023000": {
        "name": "Carne Bovina",
        "eu_barriers": "high",
        "common_issues": ["Hormônios", "Rastreabilidade", "Bem-estar animal"],
        "historical_rejections": 18,
        "sanitario_base": 72.0,
        "fitossanitario_base": 78.0,
        "logistico_base": 65.0,
        "documental_base": 68.0
    },
    "20091100": {
        "name": "Suco de Laranja",
        "eu_barriers": "medium",
        "common_issues": ["Carbendazim LMR", "Acidez", "Contaminantes"],
        "historical_rejections": 8,
        "sanitario_base": 80.0,
        "fitossanitario_base": 75.0,
        "logistico_base": 88.0,
        "documental_base": 82.0
    },
    "04090000": {
        "name": "Mel Natural",
        "eu_barriers": "medium",
        "common_issues": ["Antibióticos", "Origem botânica", "Rotulagem"],
        "historical_rejections": 6,
        "sanitario_base": 85.0,
        "fitossanitario_base": 88.0,
        "logistico_base": 90.0,
        "documental_base": 82.0
    }
}

# ==================================================================================
# CALCULADORA DE RISCO APRIMORADA
# ==================================================================================

class EnhancedRiskCalculator:
    
    def calculate(self, product: Product, rasff_6m: int, rasff_12m: int) -> dict:
        profile = NCM_RISK_PROFILES.get(product.ncm_code, {
            "sanitario_base": 85.0,
            "fitossanitario_base": 85.0,
            "logistico_base": 85.0,
            "documental_base": 85.0,
            "historical_rejections": 0
        })
        
        sanitario = profile["sanitario_base"]
        fitossanitario = profile["fitossanitario_base"]
        logistico = profile["logistico_base"]
        documental = profile["documental_base"]
        
        # Penalidades por alertas RASFF
        if rasff_6m > 0:
            sanitario -= min(rasff_6m * 5, 20)
        if rasff_12m > 5:
            sanitario -= min((rasff_12m - 5) * 3, 15)
        
        # Cálculo do score final
        final_score = (sanitario * 0.35 + fitossanitario * 0.30 + 
                      logistico * 0.20 + documental * 0.15)
        
        # Determinação do status
        if final_score >= 80:
            status = "green"
            status_label = "Baixo Risco"
        elif final_score >= 60:
            status = "yellow"
            status_label = "Risco Moderado"
        else:
            status = "red"
            status_label = "Alto Risco"
        
        recommendations = []
        if sanitario < 75:
            recommendations.append("Reforçar controles sanitários e rastreabilidade")
        if fitossanitario < 75:
            recommendations.append("Auditar uso de agrotóxicos e conformidade com LMRs")
        if rasff_6m > 0:
            recommendations.append(f"Atenção: {rasff_6m} alertas RASFF nos últimos 6 meses")
        
        return {
            "score": final_score,
            "status": status,
            "status_label": status_label,
            "components": {
                "Sanitário": sanitario,
                "Fitossanitário": fitossanitario,
                "Logístico": logistico,
                "Documental": documental
            },
            "recommendations": recommendations,
            "alerts": {
                "rasff_6m": rasff_6m,
                "rasff_12m": rasff_12m,
                "historical_rejections": profile.get("historical_rejections", 0)
            }
        }


# ==================================================================================
# GERADOR DE PDF COM REPORTLAB
# ==================================================================================

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT


class ZOIReportGenerator:
    
    def generate_risk_pdf(self, product_data: dict, risk_data: dict) -> BytesIO:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        story = []
        
        # Estilo customizado para título
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a365d'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        # Título do relatório
        story.append(Paragraph("ZOI Trade Advisory", title_style))
        story.append(Paragraph("Relatório de Análise de Risco de Exportação", styles['Heading2']))
        story.append(Spacer(1, 10*mm))
        
        # Informações do produto
        story.append(Paragraph("<b>Informações do Produto</b>", styles['Heading3']))
        
        product_info = [
            ['Campo', 'Valor'],
            ['Produto', product_data.get('name_pt', 'N/A')],
            ['Código NCM', product_data.get('ncm_code', 'N/A')],
            ['Direção', product_data.get('direction', 'N/A').upper()],
            ['Estado', product_data.get('state', 'N/A').capitalize()],
        ]
        
        product_table = Table(product_info, colWidths=[60*mm, 120*mm])
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        story.append(product_table)
        story.append(Spacer(1, 8*mm))
        
        # Score de risco
        story.append(Paragraph("<b>Avaliação de Risco</b>", styles['Heading3']))
        
        score = risk_data.get('score', 0)
        status = risk_data.get('status', 'yellow')
        
        status_colors = {
            'green': colors.HexColor('#38a169'),
            'yellow': colors.HexColor('#d69e2e'),
            'red': colors.HexColor('#e53e3e')
        }
        
        risk_info = [
            ['Métrica', 'Valor'],
            ['Score Final', f"{score:.1f}/100"],
            ['Status', risk_data.get('status_label', 'N/A')],
        ]
        
        risk_table = Table(risk_info, colWidths=[60*mm, 120*mm])
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('BACKGROUND', (0, 2), (-1, 2), status_colors.get(status, colors.yellow)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
            ('TEXTCOLOR', (0, 2), (-1, 2), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 2), (1, 2), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        story.append(risk_table)
        story.append(Spacer(1, 8*mm))
        
        # Componentes do risco
        story.append(Paragraph("<b>Componentes da Avaliação</b>", styles['Heading3']))
        
        components = risk_data.get('components', {})
        component_data = [['Componente', 'Score']]
        
        for comp_name, comp_score in components.items():
            component_data.append([comp_name, f"{comp_score:.1f}"])
        
        component_table = Table(component_data, colWidths=[90*mm, 90*mm])
        component_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        
        story.append(component_table)
        story.append(Spacer(1, 8*mm))
        
        # Alertas RASFF
        alerts = risk_data.get('alerts', {})
        if alerts.get('rasff_6m', 0) > 0 or alerts.get('rasff_12m', 0) > 0:
            story.append(Paragraph("<b>Alertas RASFF</b>", styles['Heading3']))
            
            alert_data = [
                ['Período', 'Quantidade'],
                ['Últimos 6 meses', str(alerts.get('rasff_6m', 0))],
                ['Últimos 12 meses', str(alerts.get('rasff_12m', 0))],
                ['Rejeições Históricas', str(alerts.get('historical_rejections', 0))]
            ]
            
            alert_table = Table(alert_data, colWidths=[90*mm, 90*mm])
            alert_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            
            story.append(alert_table)
            story.append(Spacer(1, 8*mm))
        
        # Recomendações
        recommendations = risk_data.get('recommendations', [])
        if recommendations:
            story.append(Paragraph("<b>Recomendações</b>", styles['Heading3']))
            
            for i, rec in enumerate(recommendations, 1):
                story.append(Paragraph(f"{i}. {rec}", styles['Normal']))
                story.append(Spacer(1, 3*mm))
        
        # Dados da Dyad (se disponíveis)
        if 'dyad_data' in risk_data and risk_data['dyad_data']:
            story.append(Spacer(1, 5*mm))
            story.append(Paragraph("<b>🧠 Dados em Tempo Real (Dyad AI)</b>", styles['Heading3']))
            
            dyad_data = risk_data['dyad_data']
            
            # LMR Data
            if 'lmr_data' in dyad_data and dyad_data['lmr_data']:
                story.append(Paragraph("<b>Limites Máximos de Resíduos (LMR)</b>", styles['Heading4']))
                
                lmr_table_data = [['Substância', 'Limite UE (mg/kg)', 'Fonte']]
                for lmr in dyad_data['lmr_data'][:5]:  # Mostrar até 5
                    lmr_table_data.append([
                        lmr.get('substance', 'N/A'),
                        str(lmr.get('eu_limit_mg_kg', 'N/A')),
                        lmr.get('source', 'N/A')
                    ])
                
                lmr_table = Table(lmr_table_data, colWidths=[70*mm, 50*mm, 60*mm])
                lmr_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1a365d')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ]))
                
                story.append(lmr_table)
                story.append(Spacer(1, 5*mm))
            
            # Barreiras
            if 'barriers' in dyad_data and dyad_data['barriers']:
                story.append(Paragraph("<b>Barreiras Não-Tarifárias</b>", styles['Heading4']))
                for barrier in dyad_data['barriers'][:5]:
                    story.append(Paragraph(f"• {barrier}", styles['Normal']))
                story.append(Spacer(1, 5*mm))
        
        # Rodapé
        story.append(Spacer(1, 10*mm))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey,
            alignment=TA_CENTER
        )
        story.append(Paragraph(
            f"Relatório gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')} | ZOI Trade Advisory © 2026",
            footer_style
        ))
        
        doc.build(story)
        buffer.seek(0)
        return buffer


# ==================================================================================
# CONFIGURAÇÃO FASTAPI
# ==================================================================================

app = FastAPI(title="ZOI Trade Advisory API", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Segurança JWT
SECRET_KEY = os.environ.get("SECRET_KEY", "zoi_secret_key_2024_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 10080  # 7 dias

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# ==================================================================================
# PYDANTIC MODELS
# ==================================================================================

class TradeDirection(str, enum.Enum):
    EXPORT = "export"
    IMPORT = "import"


class ProductState(str, enum.Enum):
    ambient = "ambient"
    frozen = "frozen"
    chilled = "chilled"


class RiskStatus(str, enum.Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class ProductBase(BaseModel):
    key: str
    name_pt: str
    name_it: str
    name_en: Optional[str] = None
    ncm_code: str
    hs_code: str
    taric_code: Optional[str] = None
    direction: TradeDirection
    state: ProductState
    category: Optional[str] = None
    shelf_life_days: Optional[int] = None
    transport_days_avg: Optional[int] = None
    temperature_min_c: Optional[float] = None
    temperature_max_c: Optional[float] = None
    requires_phytosanitary_cert: bool = True
    requires_health_cert: bool = False
    requires_origin_cert: bool = True
    critical_substances: Optional[List[str]] = None


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class RiskCalculationRequest(BaseModel):
    product_key: str
    rasff_alerts_6m: int = 0
    rasff_alerts_12m: int = 0


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    company: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str


# ==================================================================================
# DEPENDÊNCIAS E AUTENTICAÇÃO
# ==================================================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: SessionLocal = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user


# ==================================================================================
# ROTAS PRINCIPAIS
# ==================================================================================

@app.get("/")
def root():
    return {
        "service": "ZOI Trade Advisory API",
        "version": "2.1",
        "status": "operational",
        "features": [
            "Dyad AI Integration",
            "Real-time Compliance Analysis",
            "Risk Assessment",
            "PDF Export"
        ],
        "dyad_configured": bool(os.environ.get('DYAD_API_KEY'))
    }


@app.get("/api/products")
def list_products(db: SessionLocal = Depends(get_db)):
    products = db.query(Product).all()
    return [
        {
            "id": p.id,
            "key": p.key,
            "name_pt": p.name_pt,
            "name_it": p.name_it,
            "ncm_code": p.ncm_code,
            "direction": p.direction.value,
            "state": p.state.value
        }
        for p in products
    ]


@app.get("/api/products/{product_key}")
def get_product(product_key: str, db: SessionLocal = Depends(get_db)):
    product = db.query(Product).filter(Product.key == product_key).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return {
        "id": product.id,
        "key": product.key,
        "name_pt": product.name_pt,
        "name_it": product.name_it,
        "name_en": product.name_en,
        "ncm_code": product.ncm_code,
        "hs_code": product.hs_code,
        "direction": product.direction.value,
        "state": product.state.value,
        "category": product.category,
        "requires_phytosanitary_cert": product.requires_phytosanitary_cert,
        "requires_health_cert": product.requires_health_cert,
        "requires_origin_cert": product.requires_origin_cert
    }


# ==================================================================================
# ROTA PRINCIPAL: EXPORT PDF COM INTEGRAÇÃO DYAD
# ==================================================================================

@app.get("/api/products/{product_key}/export-pdf")
def export_risk_pdf(product_key: str, db: SessionLocal = Depends(get_db)):
    """
    Gera PDF de análise de risco com dados em tempo real da Dyad AI.
    
    Fluxo:
    1. Busca produto no banco
    2. Tenta obter dados atualizados via Dyad AI
    3. Se Dyad falhar, usa dados do banco como fallback
    4. Calcula risco com dados disponíveis
    5. Gera PDF profissional
    """
    print(f"\n{'='*80}")
    print(f"📄 GERAÇÃO DE PDF INICIADA - Produto: {product_key}")
    print(f"{'='*80}\n")
    
    # 1. Buscar produto no banco
    product = db.query(Product).filter(Product.key == product_key).first()
    if not product:
        print(f"❌ Produto {product_key} não encontrado no banco")
        raise HTTPException(status_code=404, detail="Product not found")
    
    print(f"✅ Produto encontrado: {product.name_pt} (NCM: {product.ncm_code})")
    
    # 2. Inicializar navegador Dyad e buscar dados em tempo real
    dyad = DyadComplianceNavigator()
    dyad_compliance_data = None
    
    try:
        print(f"\n🧠 Tentando buscar dados atualizados via Dyad AI...")
        dyad_compliance_data = dyad.search_compliance_data(
            ncm_code=product.ncm_code,
            product_name=product.name_pt,
            target_market="EU"
        )
        
        if dyad_compliance_data:
            print(f"✅ Dados da Dyad obtidos com sucesso!")
            
            # Atualizar dados do banco com informações da Dyad
            rasff_alerts = dyad_compliance_data.get('rasff_alerts', {})
            rasff_6m = rasff_alerts.get('last_6_months', 0)
            rasff_12m = rasff_alerts.get('last_12_months', 0)
            
            print(f"📊 Alertas RASFF da Dyad: 6m={rasff_6m}, 12m={rasff_12m}")
            
            # Salvar dados LMR no banco
            lmr_data_list = dyad_compliance_data.get('lmr_data', [])
            for lmr_item in lmr_data_list[:10]:  # Limitar a 10 substâncias
                substance_name = lmr_item.get('substance', '')
                eu_limit = lmr_item.get('eu_limit_mg_kg')
                
                if substance_name and eu_limit is not None:
                    existing_lmr = db.query(LMRData).filter(
                        LMRData.product_id == product.id,
                        LMRData.substance == substance_name
                    ).first()
                    
                    if not existing_lmr:
                        new_lmr = LMRData(
                            product_id=product.id,
                            substance=substance_name,
                            dest_lmr=float(eu_limit),
                            source_authority="Dyad AI / EU Database"
                        )
                        db.add(new_lmr)
                        print(f"💾 Salvando LMR: {substance_name} = {eu_limit} mg/kg")
            
            db.commit()
            
        else:
            print(f"⚠️ Dyad não retornou dados, usando fallback do banco")
            rasff_6m = 0
            rasff_12m = 0
            
    except Exception as e:
        print(f"❌ Erro ao buscar dados da Dyad: {e}")
        dyad_compliance_data = None
        rasff_6m = 0
        rasff_12m = 0
    
    # 3. Se não temos dados da Dyad, buscar última avaliação do banco
    if not dyad_compliance_data:
        latest_assessment = db.query(RiskAssessment).filter(
            RiskAssessment.product_id == product.id
        ).order_by(RiskAssessment.calculation_timestamp.desc()).first()
        
        if latest_assessment:
            rasff_6m = latest_assessment.rasff_alerts_6m
            rasff_12m = latest_assessment.rasff_alerts_12m
            print(f"📂 Usando dados da última avaliação do banco: 6m={rasff_6m}, 12m={rasff_12m}")
    
    # 4. Calcular risco
    print(f"\n🧮 Calculando score de risco...")
    calc = EnhancedRiskCalculator()
    risk_result = calc.calculate(product, rasff_6m, rasff_12m)
    
    # Adicionar dados da Dyad ao resultado
    if dyad_compliance_data:
        risk_result['dyad_data'] = dyad_compliance_data
        risk_result['data_source'] = 'dyad_ai'
    else:
        risk_result['data_source'] = 'database_fallback'
    
    print(f"✅ Score calculado: {risk_result['score']:.1f} - Status: {risk_result['status_label']}")
    
    # 5. Gerar PDF
    print(f"\n📄 Gerando PDF...")
    
    product_data = {
        "name_pt": product.name_pt,
        "name_it": product.name_it,
        "ncm_code": product.ncm_code,
        "direction": product.direction.value,
        "state": product.state.value
    }
    
    generator = ZOIReportGenerator()
    pdf_buffer = generator.generate_risk_pdf(product_data, risk_result)
    
    print(f"✅ PDF gerado com sucesso!")
    print(f"{'='*80}\n")
    
    # 6. Retornar PDF
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=zoi_risk_report_{product_key}.pdf"
        }
    )


# ==================================================================================
# SCRAPER ANVISA (Mantido como fallback secundário)
# ==================================================================================

class AnvisaLMRScraper:
    
    def __init__(self):
        self.base_url = "https://www.gov.br/anvisa/pt-br/assuntos/agrotoxicos/monografias-de-agrotoxicos"
        
    def search_lmr(self, product_name: str) -> Optional[Dict]:
        try:
            response = requests.get(self.base_url, timeout=10)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            links = soup.find_all('a', href=True)
            
            for link in links:
                link_text = link.get_text().lower()
                if any(term in link_text for term in ["carbendazim", "imazalil", "tiabendazol"]):
                    return {
                        'substance': link.get_text().strip(),
                        'lmr_mg_kg': 0.1,
                        'source': 'ANVISA',
                        'url': link['href']
                    }
            
            return None
            
        except Exception as e:
            print(f"Erro no scraper ANVISA: {e}")
            return None


def run_initial_scraping(product_name: str, product_key: str):
    print(f"\n{'='*60}")
    print(f"🔍 AUDITORIA ANVISA INICIADA")
    print(f"Produto: {product_name}")
    print(f"Key: {product_key}")
    print(f"{'='*60}\n")
    
    from sqlalchemy.orm import Session
    
    try:
        scraper = AnvisaLMRScraper()
        
        search_terms = [
            product_name,
            product_name.split()[0] if ' ' in product_name else None
        ]
        
        for term in search_terms:
            if not term:
                continue
                
            print(f"🔎 Buscando LMR para: {term}")
            results = scraper.search_lmr(term)
            
            if results:
                print(f"✅ Encontrado: {results['substance']}")
                
                with Session(engine) as session:
                    product = session.query(Product).filter(Product.key == product_key).first()
                    
                    if product:
                        existing_lmr = session.query(LMRData).filter(
                            LMRData.product_id == product.id,
                            LMRData.substance == results['substance']
                        ).first()
                        
                        if not existing_lmr:
                            new_lmr = LMRData(
                                product_id=product.id,
                                substance=results['substance'],
                                dest_lmr=results['lmr_mg_kg'],
                                source_authority=results.get('source', 'ANVISA')
                            )
                            session.add(new_lmr)
                            session.commit()
                            
                            print(f"💾 LMR salvo no banco: {results['substance']} = {results['lmr_mg_kg']} mg/kg")
                        else:
                            print(f"ℹ️ LMR já existe no banco para {results['substance']}")
                
                break
        
        print(f"\n✅ Auditoria concluída para {product_name}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ Erro na auditoria de {product_name}: {e}")
        print(f"{'='*60}\n")


# ==================================================================================
# ROTAS DE ADMINISTRAÇÃO
# ==================================================================================

@app.post("/api/admin/products")
def create_product(product_data: dict, background_tasks: BackgroundTasks):
    from sqlalchemy.orm import Session
    
    print(f"\n📝 Criando novo produto: {product_data.get('name_pt', 'N/A')}")
    
    with Session(engine) as session:
        try:
            new_p = Product(
                key=product_data["key"],
                name_pt=product_data["name_pt"],
                name_it=product_data.get("name_it", product_data["name_pt"]),
                ncm_code=product_data["ncm_code"],
                hs_code=product_data["ncm_code"][:6],
                direction=TradeDirectionDB(product_data["direction"]),
                state=ProductStateDB(product_data["state"]),
                requires_phytosanitary_cert=product_data.get("requires_phytosanitary_cert", True)
            )
            session.add(new_p)
            session.commit()
            session.refresh(new_p)
            
            print(f"✅ Produto '{new_p.name_pt}' criado com ID {new_p.id}")
            print(f"🚀 Iniciando auditoria ANVISA em segundo plano...")
            
            background_tasks.add_task(run_initial_scraping, new_p.name_pt, new_p.key)
            
            return {
                "status": "success", 
                "message": f"Produto '{new_p.name_pt}' criado com sucesso. Auditoria ANVISA iniciada.",
                "product_key": new_p.key
            }
            
        except Exception as e:
            session.rollback()
            print(f"❌ Erro ao criar produto: {e}")
            return {"status": "error", "message": str(e)}


@app.delete("/api/admin/products/{product_key}")
def delete_product(product_key: str):
    from sqlalchemy.orm import Session
    
    print(f"🗑️ Removendo produto: {product_key}")
    
    with Session(engine) as session:
        product = session.query(Product).filter(Product.key == product_key).first()
        if product:
            session.delete(product)
            session.commit()
            print(f"✅ Produto {product_key} removido com sucesso")
            return {"status": "success", "message": f"Produto {product_key} removido"}
        
        print(f"⚠️ Produto {product_key} não encontrado")
        return {"status": "error", "message": "Produto não encontrado"}


@app.post("/api/risk/calculate")
def calculate_risk(request: RiskCalculationRequest, db: SessionLocal = Depends(get_db)):
    print(f"🧮 Calculando risco para produto: {request.product_key}")
    
    product = db.query(Product).filter(Product.key == request.product_key).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    rasff_alerts_6m = request.rasff_alerts_6m
    rasff_alerts_12m = request.rasff_alerts_12m
    
    if rasff_alerts_6m == 0 and rasff_alerts_12m == 0:
        print("📊 Nenhum alerta RASFF fornecido, usando perfil histórico do NCM")
        profile = NCM_RISK_PROFILES.get(product.ncm_code)
        if profile:
            rasff_alerts_12m = profile.get('historical_rejections', 0)
            rasff_alerts_6m = min(rasff_alerts_12m // 2, rasff_alerts_12m)
            print(f"📈 Alertas estimados: 6m={rasff_alerts_6m}, 12m={rasff_alerts_12m}")
    
    calc = EnhancedRiskCalculator()
    result = calc.calculate(product, rasff_alerts_6m, rasff_alerts_12m)
    
    try:
        assessment = RiskAssessment(
            product_id=product.id,
            final_score=result['score'],
            status=RiskStatusDB(result['status']),
            rasff_score=result['components']['Sanitário'],
            lmr_score=result['components']['Fitossanitário'],
            phyto_score=result['components']['Fitossanitário'],
            logistic_score=result['components']['Logístico'],
            penalty=100 - result['score'],
            rasff_alerts_6m=rasff_alerts_6m,
            rasff_alerts_12m=rasff_alerts_12m,
            recommendations=result['recommendations']
        )
        db.add(assessment)
        db.commit()
        print(f"✅ Avaliação de risco salva no banco de dados")
    except Exception as e:
        print(f"⚠️ Erro ao salvar avaliação: {e}")
    
    return {
        "score": float(result["score"]),
        "status": str(result["status"]),
        "status_label": str(result["status_label"]),
        "components": {
            "Sanitário": float(result["components"]["Sanitário"]),
            "Fitossanitário": float(result["components"]["Fitossanitário"]),
            "Logístico": float(result["components"]["Logístico"]),
            "Documental": float(result["components"]["Documental"])
        },
        "recommendations": [str(r) for r in result["recommendations"]],
        "alerts": {
            "rasff_6m": int(result["alerts"]["rasff_6m"]),
            "rasff_12m": int(result["alerts"]["rasff_12m"]),
            "historical_rejections": int(result["alerts"]["historical_rejections"])
        },
        "product_info": {
            "name": str(product.name_pt), 
            "ncm": str(product.ncm_code),
            "direction": str(product.direction.value)
        }
    }


# ==================================================================================
# ROTAS DE USUÁRIOS E AUTENTICAÇÃO
# ==================================================================================

@app.post("/api/users", status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: SessionLocal = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    db_user = User(
        email=user.email,
        hashed_password=get_password_hash(user.password),
        full_name=user.full_name,
        company=user.company
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {"message": "User created successfully", "email": db_user.email}


@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: SessionLocal = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/admin/stats")
def get_admin_stats(db: SessionLocal = Depends(get_db)):
    total_products = db.query(Product).count()
    total_assessments = db.query(RiskAssessment).count()
    total_users = db.query(User).count()
    
    green_count = db.query(RiskAssessment).filter(RiskAssessment.status == RiskStatusDB.GREEN).count()
    yellow_count = db.query(RiskAssessment).filter(RiskAssessment.status == RiskStatusDB.YELLOW).count()
    red_count = db.query(RiskAssessment).filter(RiskAssessment.status == RiskStatusDB.RED).count()
    
    return {
        "total_products": total_products,
        "total_assessments": total_assessments,
        "total_users": total_users,
        "status_distribution": {
            "green": green_count,
            "yellow": yellow_count,
            "red": red_count
        }
    }


# ==================================================================================
# INICIALIZAÇÃO
# ==================================================================================

if __name__ == "__main__":
    import uvicorn
    Base.metadata.create_all(bind=engine)
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*80}")
    print(f"🚀 ZOI Trade Advisory API v2.1 - Iniciando")
    print(f"{'='*80}")
    print(f"🔌 Porta: {port}")
    print(f"🧠 Dyad AI: {'✅ Configurado' if os.environ.get('DYAD_API_KEY') else '❌ Não configurado'}")
    print(f"💾 Database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Local'}")
    print(f"{'='*80}\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
