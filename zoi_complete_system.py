"""
ZOI Trade Advisory - Complete Production System
Version 2.0 - Commercial Phase with Enhanced Risk Analysis
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
from typing import Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from io import BytesIO

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel, EmailStr
from jose import JWTError, jwt
from passlib.context import CryptContext

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


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://zoi_user:IN3LI5N6OshhlVIDetxmCXhX01es3nK8@dpg-d5pkoeer433s73ddm970-a/zoi_db")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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
        "common_issues": ["Antibióticos", "Pólen OGM", "Adulteração"],
        "historical_rejections": 6,
        "sanitario_base": 85.0,
        "fitossanitario_base": 88.0,
        "logistico_base": 90.0,
        "documental_base": 80.0
    },
    "15092000": {
        "name": "Azeite de Oliva",
        "eu_barriers": "low",
        "common_issues": ["Autenticidade", "Indicação geográfica"],
        "historical_rejections": 1,
        "sanitario_base": 95.0,
        "fitossanitario_base": 92.0,
        "logistico_base": 88.0,
        "documental_base": 90.0
    },
    "22042100": {
        "name": "Vinho Tinto",
        "eu_barriers": "low",
        "common_issues": ["Sulfitos", "Rotulagem"],
        "historical_rejections": 1,
        "sanitario_base": 94.0,
        "fitossanitario_base": 96.0,
        "logistico_base": 85.0,
        "documental_base": 88.0
    }
}


class ANVISAScraper:
    BASE_URL = "https://www.gov.br/anvisa/pt-br"
    MONOGRAFIA_URL = f"{BASE_URL}/assuntos/agrotoxicos/monografia"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_lmr_for_substance(self, substance: str, crop: str) -> Optional[Dict]:
        print(f"🔍 Buscando LMR para {substance} × {crop}...")
        
        try:
            search_url = f"{self.MONOGRAFIA_URL}?ingrediente={substance.lower()}"
            
            print(f"🌐 Acessando ANVISA: {search_url}")
            response = self.session.get(search_url, timeout=15)
            
            if response.status_code != 200:
                print(f"⚠️ ANVISA retornou status {response.status_code} - usando fallback")
                result = self._get_fallback_lmr(substance, crop)
                result['source'] = 'PRESUMIDO - AGUARDANDO ATUALIZAÇÃO'
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            lmr_table = soup.find('table', {'class': 'lmr-table'})
            
            if not lmr_table:
                lmr_table = soup.find('table', string=re.compile('Limite Máximo'))
            
            if lmr_table:
                print(f"📊 Tabela LMR encontrada, processando...")
                rows = lmr_table.find_all('tr')
                
                for row in rows:
                    cols = row.find_all('td')
                    
                    if len(cols) >= 2:
                        crop_cell = cols[0].text.strip().lower()
                        
                        if crop.lower() in crop_cell:
                            lmr_text = cols[1].text.strip()
                            lmr_value = self._extract_number(lmr_text)
                            
                            if lmr_value is not None:
                                print(f"✅ LMR oficial encontrado: {lmr_value} mg/kg")
                                return {
                                    'substance': substance,
                                    'crop': crop,
                                    'lmr_mg_kg': lmr_value,
                                    'source': 'ANVISA',
                                    'url': search_url
                                }
            
            print(f"⚠️ Dados não encontrados na ANVISA - usando valores presumidos")
            result = self._get_fallback_lmr(substance, crop)
            result['source'] = 'PRESUMIDO - AGUARDANDO ATUALIZAÇÃO'
            return result
            
        except requests.Timeout:
            print(f"⏱️ Timeout ao acessar ANVISA - usando fallback")
            result = self._get_fallback_lmr(substance, crop)
            result['source'] = 'PRESUMIDO - AGUARDANDO ATUALIZAÇÃO'
            return result
            
        except Exception as e:
            print(f"❌ Erro ao processar ANVISA ({e}) - usando fallback")
            result = self._get_fallback_lmr(substance, crop)
            result['source'] = 'PRESUMIDO - AGUARDANDO ATUALIZAÇÃO'
            return result
    
    def _extract_number(self, text: str) -> Optional[float]:
        match = re.search(r'(\d+\.?\d*)', text.replace(',', '.'))
        return float(match.group(1)) if match else None
    
    def _get_fallback_lmr(self, substance: str, crop: str) -> Dict:
        print(f"📋 Usando base de dados interna para {substance} × {crop}")
        
        fallback_data = {
            ('Glifosato', 'Soja'): 10.0,
            ('Glifosato', 'Café'): 1.0,
            ('Glifosato', 'Grãos'): 10.0,
            ('Carbendazim', 'Laranja'): 2.0,
            ('Carbendazim', 'Café'): 0.1,
            ('Clorpirifós', 'Soja'): 0.5,
            ('Tiabendazol', 'Laranja'): 5.0,
            ('Genérico', 'Carne'): 0.05,
            ('Genérico', 'Suco'): 0.5,
            ('Genérico', 'Polpa'): 0.3,
            ('Genérico', 'Mel'): 0.1,
        }
        
        lmr = fallback_data.get((substance, crop), 1.0)
        
        for key, value in fallback_data.items():
            if crop.lower() in key[1].lower():
                lmr = value
                break
        
        print(f"💾 Valor presumido: {lmr} mg/kg")
        
        return {
            'substance': substance,
            'crop': crop,
            'lmr_mg_kg': lmr,
            'source': 'FALLBACK',
            'url': self.MONOGRAFIA_URL
        }

class ProductResponse(BaseModel):
    id: int
    key: str
    name_pt: str
    name_it: str
    ncm_code: str
    direction: str
    state: str
    shelf_life_days: Optional[int]
    
    class Config:
        from_attributes = True


class RiskCalculationRequest(BaseModel):
    product_key: str
    rasff_alerts_6m: int = 0
    rasff_alerts_12m: int = 0
    lmr_data: List[dict] = []
    phyto_alerts: List[dict] = []
    transport_days: Optional[int] = None


class RiskCalculationResponse(BaseModel):
    score: float
    status: str
    components: dict
    recommendations: List[str]
    product_info: dict


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str

class EnhancedRiskCalculator:
    """
    Motor de cálculo de risco ZOI.
    Avalia parâmetros Sanitários, Fitossanitários, Logísticos e Documentais.
    """
    def calculate(self, product, rasff_6m: int, rasff_12m: int) -> dict:
        # Recupera perfil base do NCM ou usa valores padrão
        profile = NCM_RISK_PROFILES.get(product.ncm_code, {
            "sanitario_base": 85.0,
            "fitossanitario_base": 80.0,
            "logistico_base": 85.0,
            "documental_base": 80.0,
            "historical_rejections": 0
        })

        # 1. Cálculo de Componentes
        # Penalidade RASFF: -10 pontos por alerta recente (6m), -4 por alerta antigo (12m)
        sanitario = max(0, profile['sanitario_base'] - (rasff_6m * 10) - (rasff_12m * 4))
        
        # Fitossanitário: Baseado no estado do produto (congelados têm menos risco que frescos)
        fitossanitario = profile['fitossanitario_base']
        if product.state.value == 'frozen':
            fitossanitario = min(100, fitossanitario + 10)
            
        logistico = profile['logistico_base']
        documental = profile['documental_base']

        # 2. Score Final (Média Ponderada)
        score = (sanitario * 0.4) + (fitossanitario * 0.3) + (logistico * 0.15) + (documental * 0.15)
        
        # 3. Definição de Status
        if score >= 80:
            status = "green"
            label = "Baixo Risco"
        elif score >= 60:
            status = "yellow"
            label = "Risco Moderado"
        else:
            status = "red"
            label = "Alto Risco"

        # 4. Recomendações Automáticas
        recommendations = []
        if sanitario < 70:
            recommendations.append("Reforçar análises laboratoriais de contaminantes químicos.")
        if fitossanitario < 75:
            recommendations.append("Verificar conformidade com a Instrução Normativa de pragas quarentenárias.")
        if status == "red":
            recommendations.append("Alerta: Recomenda-se auditoria prévia no fornecedor antes do embarque.")
        
        if not recommendations:
            recommendations.append("Manter protocolos atuais de compliance.")

        return {
            "score": round(score, 1),
            "status": status,
            "status_label": label,
            "components": {
                "Sanitário": round(sanitario, 1),
                "Fitossanitário": round(fitossanitario, 1),
                "Logístico": round(logistico, 1),
                "Documental": round(documental, 1)
            },
            "recommendations": recommendations,
            "alerts": {
                "rasff_6m": rasff_6m,
                "rasff_12m": rasff_12m,
                "historical_rejections": profile.get('historical_rejections', 0)
            }
        }

app = FastAPI(
    title="ZOI Trade Advisory API",
    description="Sistema Bilateral de Compliance Sanitária e Fitossanitária",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================================================
# ROTA PDF - PRIMEIRA ROTA REGISTRADA (MÁXIMA PRECEDÊNCIA)
# ==================================================================================
@app.get("/api/products/{product_key}/export-pdf")
def export_risk_pdf(product_key: str):
    """
    Endpoint de exportação PDF - VERSÃO CORRIGIDA COM PRECEDÊNCIA TOTAL
    """
    from io import BytesIO
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    
    print(f"📄 [PDF ENDPOINT ATIVADO] Gerando PDF para: {product_key}")
    
    # Criar sessão dedicada para este endpoint
    db = SessionLocal()
    
    try:
        # Buscar produto
        product = db.query(Product).filter(Product.key == product_key).first()
        if not product:
            db.close()
            return Response(
                content=b"Produto nao encontrado",
                status_code=404,
                media_type="text/plain"
            )
        
        print(f"✅ Produto encontrado: {product.name_pt}")
        
        # Buscar última avaliação de risco
        latest_assessment = db.query(RiskAssessment)\
            .filter(RiskAssessment.product_id == product.id)\
            .order_by(RiskAssessment.calculation_timestamp.desc())\
            .first()
        
        # Se não houver avaliação, calcular uma nova
        if not latest_assessment:
            print("🔄 Calculando nova avaliação de risco...")
            calc = EnhancedRiskCalculator()
            result = calc.calculate(product, 0, 0)
            
            assessment_data = {
                "score": result['score'],
                "status": result['status'],
                "status_label": result['status_label'],
                "components": result['components'],
                "recommendations": result['recommendations'],
                "alerts": result['alerts']
            }
        else:
            print(f"📊 Usando avaliação existente (Score: {latest_assessment.final_score})")
            assessment_data = {
                "score": latest_assessment.final_score,
                "status": latest_assessment.status.value,
                "status_label": "Baixo Risco" if latest_assessment.status.value == "green" else 
                               "Risco Moderado" if latest_assessment.status.value == "yellow" else "Alto Risco",
                "components": {
                    "Sanitario": latest_assessment.rasff_score or 85.0,
                    "Fitossanitario": latest_assessment.lmr_score or 80.0,
                    "Logistico": latest_assessment.logistic_score or 88.0,
                    "Documental": 82.0
                },
                "recommendations": latest_assessment.recommendations or ["Manter protocolos atuais de compliance."],
                "alerts": {
                    "rasff_6m": latest_assessment.rasff_alerts_6m,
                    "rasff_12m": latest_assessment.rasff_alerts_12m,
                    "historical_rejections": 0
                }
            }
        
        # Criar buffer para o PDF
        buffer = BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        
        # Configurar título do documento
        c.setTitle(f"ZOI Risk Report - {product_key}")
        
        # ===== HEADER =====
        c.setFillColorRGB(0.12, 0.25, 0.69)  # Azul escuro
        c.rect(0, height - 3*cm, width, 3*cm, fill=True, stroke=False)
        
        c.setFillColorRGB(1, 1, 1)  # Branco
        c.setFont("Helvetica-Bold", 24)
        c.drawString(2*cm, height - 2*cm, "ZOI Trade Advisory")
        
        c.setFont("Helvetica", 12)
        c.drawString(2*cm, height - 2.5*cm, "Relatorio Executivo de Analise de Risco Sanitario e Fitossanitario")
        
        # ===== INFORMAÇÕES DO PRODUTO =====
        y_position = height - 5*cm
        
        c.setFillColorRGB(0.12, 0.25, 0.69)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_position, "Informacoes do Produto")
        
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 11)
        y_position -= 0.8*cm
        
        c.drawString(2*cm, y_position, f"Produto: {product.name_pt}")
        y_position -= 0.6*cm
        c.drawString(2*cm, y_position, f"Codigo NCM: {product.ncm_code}")
        y_position -= 0.6*cm
        
        direction_text = 'Exportacao BR -> IT' if product.direction.value == 'export' else 'Importacao IT -> BR'
        c.drawString(2*cm, y_position, f"Direcao Comercial: {direction_text}")
        y_position -= 0.6*cm
        c.drawString(2*cm, y_position, f"Estado: {product.state.value.capitalize()}")
        
        # ===== SCORE DE RISCO =====
        y_position -= 1.5*cm
        
        c.setFillColorRGB(0.12, 0.25, 0.69)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_position, "Score de Risco Global")
        
        y_position -= 0.8*cm
        
        # Definir cor do badge baseado no status
        if assessment_data['status'] == 'green':
            c.setFillColorRGB(0.09, 0.39, 0.20)  # Verde escuro
        elif assessment_data['status'] == 'yellow':
            c.setFillColorRGB(0.52, 0.30, 0.05)  # Amarelo escuro
        else:
            c.setFillColorRGB(0.60, 0.11, 0.11)  # Vermelho escuro
        
        c.setFont("Helvetica-Bold", 20)
        c.drawString(2*cm, y_position, f"{assessment_data['score']:.1f}/100 - {assessment_data['status_label']}")
        
        c.setFillColorRGB(0.39, 0.45, 0.55)
        c.setFont("Helvetica", 9)
        y_position -= 0.5*cm
        c.drawString(2*cm, y_position, f"Data da analise: {datetime.now().strftime('%d/%m/%Y as %H:%M')}")
        
        # ===== COMPONENTES DE RISCO =====
        y_position -= 1.5*cm
        
        c.setFillColorRGB(0.12, 0.25, 0.69)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_position, "Componentes de Risco")
        
        y_position -= 1*cm
        
        # Desenhar barras de progresso para cada componente
        components = [
            ("Sanitario", assessment_data['components'].get('Sanitario', assessment_data['components'].get('Sanitário', 85.0))),
            ("Fitossanitario", assessment_data['components'].get('Fitossanitario', assessment_data['components'].get('Fitossanitário', 80.0))),
            ("Logistico", assessment_data['components'].get('Logistico', assessment_data['components'].get('Logístico', 88.0))),
            ("Documental", assessment_data['components'].get('Documental', 82.0))
        ]
        
        c.setFont("Helvetica", 10)
        for comp_name, comp_value in components:
            c.setFillColorRGB(0, 0, 0)
            c.drawString(2*cm, y_position, f"{comp_name}: {comp_value:.1f}/100")
            
            # Desenhar barra de fundo
            c.setFillColorRGB(0.89, 0.91, 0.94)
            c.rect(8*cm, y_position - 0.2*cm, 10*cm, 0.4*cm, fill=True, stroke=False)
            
            # Desenhar barra de progresso
            c.setFillColorRGB(0.23, 0.51, 0.98)
            bar_width = (comp_value / 100) * 10*cm
            c.rect(8*cm, y_position - 0.2*cm, bar_width, 0.4*cm, fill=True, stroke=False)
            
            y_position -= 0.8*cm
        
        # ===== RECOMENDAÇÕES =====
        y_position -= 1*cm
        
        c.setFillColorRGB(0.12, 0.25, 0.69)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, y_position, "Recomendacoes Estrategicas")
        
        y_position -= 0.8*cm
        
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 9)
        
        for idx, rec in enumerate(assessment_data['recommendations'][:5], 1):
            # Quebrar texto longo
            if len(rec) > 90:
                rec = rec[:87] + "..."
            
            c.drawString(2.5*cm, y_position, f"{idx}. {rec}")
            y_position -= 0.6*cm
            
            if y_position < 3*cm:
                break
        
        # ===== FOOTER =====
        c.setFillColorRGB(0.39, 0.45, 0.55)
        c.setFont("Helvetica", 8)
        c.drawString(2*cm, 2*cm, "ZOI Trade Advisory - Sistema Bilateral de Compliance Sanitaria e Fitossanitaria")
        c.drawString(2*cm, 1.5*cm, f"Relatorio gerado em {datetime.now().strftime('%d/%m/%Y as %H:%M:%S')}")
        
        # Finalizar PDF
        c.showPage()
        c.save()
        
        # Obter bytes do PDF
        pdf_bytes = buffer.getvalue()
        buffer.close()
        
        print(f"✅ PDF gerado com sucesso ({len(pdf_bytes)} bytes)")
        
        # Fechar sessão do banco
        db.close()
        
        # Retornar PDF com headers de force-download e no-cache
        filename = f"ZOI_Risk_Report_{product_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "application/pdf",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        print(f"❌ ERRO ao gerar PDF: {str(e)}")
        import traceback
        traceback.print_exc()
        
        db.close()
        
        return Response(
            content=f"Erro ao gerar PDF: {str(e)}".encode(),
            status_code=500,
            media_type="text/plain"
        )


# ==================================================================================
# CONFIGURAÇÕES DE SEGURANÇA E AUTENTICAÇÃO
# ==================================================================================

SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
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


@app.get("/")
def root():  
    return {
        "message": "ZOI Trade Advisory API v2.0",
        "status": "operational",
        "endpoints": {
            "products": "/api/products",
            "risk_calculation": "/api/risk/calculate",
            "admin": "/api/admin",
            "export_pdf": "/api/products/{key}/export-pdf"
        }
    }


@app.get("/api/admin/seed-database")
def seed_database(background_tasks: BackgroundTasks):
    from sqlalchemy.orm import Session
    
    print("📄 Iniciando seed do banco de dados...")
    
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
    print("✅ Tabelas criadas com sucesso")
    
    with Session(engine) as session:
        products_list = [
            {"key": "soja_grao", "name": "Soja em Grãos", "ncm": "12019000", "dir": "export", "state": "ambient"},
            {"key": "cafe_cru", "name": "Café Cru em Grão", "ncm": "09011110", "dir": "export", "state": "ambient"},
            {"key": "carne_bovina", "name": "Carne Bovina", "ncm": "02023000", "dir": "export", "state": "frozen"},
            {"key": "suco_laranja", "name": "Suco de Laranja", "ncm": "20091100", "dir": "export", "state": "frozen"},
            {"key": "acai_polpa", "name": "Polpa de Açaí", "ncm": "08119050", "dir": "export", "state": "frozen"},
            {"key": "mel_natural", "name": "Mel Natural", "ncm": "04090000", "dir": "export", "state": "ambient"},
            {"key": "azeite_oliva", "name": "Azeite de Oliva", "ncm": "15092000", "dir": "import", "state": "ambient"},
            {"key": "vinho_tinto", "name": "Vinho Tinto", "ncm": "22042100", "dir": "import", "state": "ambient"},
            {"key": "limao_siciliano", "name": "Limão Siciliano", "ncm": "08055000", "dir": "import", "state": "ambient"},
            {"key": "maca_fresca", "name": "Maçã Fresca", "ncm": "08081000", "dir": "export", "state": "chilled"},
        ]
        
        created_products = []
        
        for item in products_list:
            print(f"📦 Criando produto: {item['name']}")
            new_p = Product(
                key=item["key"],
                name_pt=item["name"],
                name_it=item["name"],
                ncm_code=item["ncm"],
                hs_code=item["ncm"][:6],
                direction=TradeDirectionDB(item["dir"]),
                state=ProductStateDB(item["state"]),
                requires_phytosanitary_cert=True
            )
            session.add(new_p)
            session.flush()
            created_products.append((new_p.name_pt, new_p.key))
        
        session.commit()
        total = session.query(Product).count()
        
        print(f"✅ {total} produtos criados no banco")
    
    print("🚀 Iniciando auditoria assíncrona em segundo plano...")
    for product_name, product_key in created_products:
        background_tasks.add_task(run_initial_scraping, product_name, product_key)
    
    return {
        "status": "success", 
        "total": total,
        "message": f"{total} produtos criados. Auditoria ANVISA iniciada em segundo plano."
    }


@app.get("/api/products")
def get_products(db: SessionLocal = Depends(get_db)):
    try:
        products = db.query(Product).all()
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/products/{product_key}", response_model=ProductResponse)
def get_product(product_key: str, db: SessionLocal = Depends(get_db)):
    product = db.query(Product).filter(Product.key == product_key).first()
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


def run_initial_scraping(product_name: str, product_key: str):
    print(f"\n{'='*60}")
    print(f"🔬 AUDITORIA ANVISA: {product_name}")
    print(f"{'='*60}")
    
    try:
        scraper = ANVISAScraper()
        
        substances = ["Glifosato", "Genérico"]
        
        for substance in substances:
            print(f"\n🧪 Testando substância: {substance}")
            results = scraper.get_lmr_for_substance(substance, product_name)
            
            if results:
                from sqlalchemy.orm import Session
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
                            print(f"🔍 Fonte: {results.get('source', 'ANVISA')}")
                        else:
                            print(f"ℹ️ LMR já existe no banco para {results['substance']}")
                
                break
        
        print(f"\n✅ Auditoria concluída para {product_name}")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ Erro na auditoria de {product_name}: {e}")
        print(f"{'='*60}\n")


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
                "message": f"Produto '{new_p.name_pt}' criado com sucesso. Auditoria ANVISA iniciada em segundo plano.",
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

    
if __name__ == "__main__":
    import uvicorn
    Base.metadata.create_all(bind=engine)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
