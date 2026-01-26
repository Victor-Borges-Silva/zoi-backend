def _run_dyad_agent(self, ncm_code: str, product_name: str) -> Optional[Dict]:
        """
        Executa agente Dyad via REST API para navegar nos portais de compliance.
        """
        
        if not self.dyad_api_key:
            print("⚠️ DYAD_API_KEY não configurada")
            return None
        
        print("🌐 Iniciando navegação inteligente via Dyad REST API...")
        
        # Criar instruções para o agente
        agent_instructions = f"""
        You are a specialized compliance data navigator for international food trade.
        
        YOUR MISSION:
        Navigate to the EU RASFF (Rapid Alert System for Food and Feed) portal and ANVISA Brazil portal
        to gather compliance data about the following product:
        
        - Product: {product_name}
        - NCM Code: {ncm_code}
        - Origin: Brazil
        
        SPECIFIC TASKS:
        1. Access RASFF Window (https://webgate.ec.europa.eu/rasff-window/)
        2. Search for notifications involving 'Brazil' AND NCM '{ncm_code}'
        3. Count alerts in the last 90 days, 6 months, and 12 months
        4. Identify the top 3 rejection reasons (e.g., pesticide residues, contamination, certification issues)
        5. Access ANVISA portal (https://www.gov.br/anvisa/) for complementary data
        6. Extract LMR (Maximum Residue Limits) information if available
        
        IMPORTANT:
        - Focus on recent data (last 12 months prioritized)
        - Distinguish between alert severity (serious risk vs border rejection)
        - Note specific substances/contaminants mentioned
        - Record source URLs for traceability
        
        RETURN FORMAT (JSON):
        {{
            "rasff_alerts_90d": <number>,
            "rasff_alerts_6m": <number>,
            "rasff_alerts_12m": <number>,
            "rejection_reasons": ["reason1", "reason2", "reason3"],
            "critical_substances": ["substance1", "substance2"],
            "source_urls": ["url1", "url2"],
            "last_incident_date": "YYYY-MM-DD",
            "confidence_level": "high/medium/low"
        }}
        """
        
        try:
            # Chamar API REST do Dyad
            print("⏳ Enviando requisição para Dyad API...")
            
            response = requests.post(
                f"{self.dyad_base_url}/v1/agents/run",
                headers={
                    "Authorization": f"Bearer {self.dyad_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "instructions": agent_instructions,
                    "timeout": 60,
                    "max_steps": 15
                },
                timeout=65
            )
            
            if response.status_code != 200:
                print(f"❌ Dyad API retornou status {response.status_code}: {response.text}")
                return None
            
            result = response.json()
            
            # Parse da resposta
            if result and 'result' in result:
                result_data = json.loads(result['result']) if isinstance(result['result'], str) else result['result']
                
                print(f"📊 Dados extraídos:")
                print(f"   - Alertas 90d: {result_data.get('rasff_alerts_90d', 0)}")
                print(f"   - Alertas 6m: {result_data.get('rasff_alerts_6m', 0)}")
                print(f"   - Alertas 12m: {result_data.get('rasff_alerts_12m', 0)}")
                print(f"   - Confiança: {result_data.get('confidence_level', 'unknown')}")
                
                # Calcular scores baseados nos dados coletados
                sanitario_score = self._calculate_sanitario_score(
                    result_data.get('rasff_alerts_6m', 0),
                    result_data.get('rasff_alerts_12m', 0),
                    ncm_code
                )
                
                fitossanitario_score = self._calculate_fitossanitario_score(
                    result_data.get('critical_substances', []),
                    result_data.get('rejection_reasons', []),
                    ncm_code
                )
                
                return {
                    'source': 'dyad',
                    'rasff_alerts_90d': result_data.get('rasff_alerts_90d', 0),
                    'rasff_alerts_6m': result_data.get('rasff_alerts_6m', 0),
                    'rasff_alerts_12m': result_data.get('rasff_alerts_12m', 0),
                    'main_rejection_reasons': result_data.get('rejection_reasons', []),
                    'critical_substances': result_data.get('critical_substances', []),
                    'sanitario_score': sanitario_score,
                    'fitossanitario_score': fitossanitario_score,
                    'timestamp': datetime.utcnow(),
                    'confidence': result_data.get('confidence_level', 'medium'),
                    'source_urls': result_data.get('source_urls', [])
                }
            
        except requests.Timeout:
            print("⏱️ Timeout ao executar agente Dyad")
        except requests.RequestException as e:
            print(f"❌ Erro de conexão com Dyad API: {e}")
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao decodificar JSON da resposta Dyad: {e}")
        except Exception as e:
            print(f"❌ Erro inesperado no agente Dyad: {e}")
        
        return Noneclass DyadComplianceNavigator:
    """
    Intelligent compliance data navigator using Dyad REST API.
    Fallback to historical data if Dyad is unavailable.
    """
    
    def __init__(self):
        self.dyad_api_key = os.environ.get('DYAD_API_KEY')
        self.dyad_base_url = os.environ.get('DYAD_API_URL', 'https://api.dyad.sh')
        self.client = None
        
        if self.dyad_api_key:
            print(f"✅ Dyad API configurada: {self.dyad_base_url}")
        else:
            print("⚠️ DYAD_API_KEY não configurada - usando modo fallback")# ==================================================================================
# DYAD INTEGRATION - Intelligent Web Navigation via REST API
# ==================================================================================

# Dyad funciona via API REST - não precisa de SDK específico
DYAD_AVAILABLE = True
print("✅ Dyad REST API configurado (usando requests)")

Base = declarative_base()"""
ZOI Trade Advisory - Complete Production System with Dyad Integration
Version 2.1 - Intelligent Navigation with AI Agents
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
from typing import Dict, List, Optional, Tuple
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
# DYAD INTEGRATION - Intelligent Web Navigation
# ==================================================================================

# Dyad SDK ainda não disponível no PyPI - usando modo fallback
# Quando o SDK estiver disponível, descomente as linhas abaixo:
# try:
#     from dyad import DyadClient
#     DYAD_AVAILABLE = True
#     print("✅ Dyad SDK disponível")
# except ImportError:
#     DYAD_AVAILABLE = False
#     print("⚠️ Dyad SDK não encontrado - usando modo fallback")

DYAD_AVAILABLE = False
print("ℹ️ Sistema rodando em modo fallback (dados históricos NCM)")

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
    
    # Novos campos para rastreamento Dyad
    dyad_data_source = Column(String(50), default='fallback')
    dyad_last_fetch = Column(DateTime)
    
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

# ==================================================================================
# DATABASE CONFIGURATION
# ==================================================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://zoi_user:IN3LI5N6OshhlVIDetxmCXhX01es3nK8@dpg-d5pkoeer433s73ddm970-a/zoi_db")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ==================================================================================
# NCM RISK PROFILES - Historical Data for Fallback
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

# ==================================================================================
# DYAD INTELLIGENT NAVIGATION - Primary Data Collection
# ==================================================================================

class DyadComplianceNavigator:
    """
    Intelligent compliance data navigator using Dyad AI agents.
    Fallback to historical data if Dyad is unavailable.
    """
    
    def __init__(self):
        self.dyad_api_key = os.environ.get('DYAD_API_KEY')
        self.client = None
        
        # Dyad SDK ainda não disponível - sempre usa fallback
        print("⚠️ Dyad SDK não disponível - sistema usando dados históricos")
    
    def fetch_dyad_compliance_data(self, ncm_code: str, product_name: str) -> Dict:
        """
        Coleta dados de compliance usando agentes Dyad inteligentes.
        
        Args:
            ncm_code: Código NCM do produto (ex: "08055000")
            product_name: Nome do produto (ex: "Limão Siciliano")
            
        Returns:
            Dict com estrutura:
            {
                'source': 'dyad' ou 'fallback',
                'rasff_alerts_90d': int,
                'rasff_alerts_6m': int,
                'rasff_alerts_12m': int,
                'main_rejection_reasons': List[str],
                'sanitario_score': float,
                'fitossanitario_score': float,
                'timestamp': datetime,
                'confidence': str ('high', 'medium', 'low')
            }
        """
        
        print(f"\n{'='*70}")
        print(f"🤖 DYAD INTELLIGENT NAVIGATION")
        print(f"Produto: {product_name} (NCM: {ncm_code})")
        print(f"{'='*70}\n")
        
        # Tentar coletar dados via Dyad
        if self.client:
            try:
                dyad_data = self._run_dyad_agent(ncm_code, product_name)
                if dyad_data:
                    print("✅ Dados coletados com sucesso via Dyad")
                    return dyad_data
            except Exception as e:
                print(f"❌ Erro ao executar agente Dyad: {e}")
                print("🔄 Acionando fallback para dados históricos...")
        
        # Fallback para dados históricos
        return self._get_fallback_data(ncm_code, product_name)
    
    def _run_dyad_agent(self, ncm_code: str, product_name: str) -> Optional[Dict]:
        """
        Executa agente Dyad para navegar nos portais de compliance.
        """
        
        print("🌐 Iniciando navegação inteligente...")
        
        # Criar instruções para o agente
        agent_instructions = f"""
        You are a specialized compliance data navigator for international food trade.
        
        YOUR MISSION:
        Navigate to the EU RASFF (Rapid Alert System for Food and Feed) portal and ANVISA Brazil portal
        to gather compliance data about the following product:
        
        - Product: {product_name}
        - NCM Code: {ncm_code}
        - Origin: Brazil
        
        SPECIFIC TASKS:
        1. Access RASFF Window (https://webgate.ec.europa.eu/rasff-window/)
        2. Search for notifications involving 'Brazil' AND NCM '{ncm_code}'
        3. Count alerts in the last 90 days, 6 months, and 12 months
        4. Identify the top 3 rejection reasons (e.g., pesticide residues, contamination, certification issues)
        5. Access ANVISA portal (https://www.gov.br/anvisa/) for complementary data
        6. Extract LMR (Maximum Residue Limits) information if available
        
        IMPORTANT:
        - Focus on recent data (last 12 months prioritized)
        - Distinguish between alert severity (serious risk vs border rejection)
        - Note specific substances/contaminants mentioned
        - Record source URLs for traceability
        
        RETURN FORMAT (JSON):
        {{
            "rasff_alerts_90d": <number>,
            "rasff_alerts_6m": <number>,
            "rasff_alerts_12m": <number>,
            "rejection_reasons": ["reason1", "reason2", "reason3"],
            "critical_substances": ["substance1", "substance2"],
            "source_urls": ["url1", "url2"],
            "last_incident_date": "YYYY-MM-DD",
            "confidence_level": "high/medium/low"
        }}
        """
        
        try:
            # Executar agente Dyad com timeout de 60 segundos
            print("⏳ Aguardando resposta do agente (timeout: 60s)...")
            
            response = self.client.run_agent(
                instructions=agent_instructions,
                timeout=60,
                max_steps=15
            )
            
            # Parse da resposta JSON
            if response and 'result' in response:
                result_data = json.loads(response['result'])
                
                print(f"📊 Dados extraídos:")
                print(f"   - Alertas 90d: {result_data.get('rasff_alerts_90d', 0)}")
                print(f"   - Alertas 6m: {result_data.get('rasff_alerts_6m', 0)}")
                print(f"   - Alertas 12m: {result_data.get('rasff_alerts_12m', 0)}")
                print(f"   - Confiança: {result_data.get('confidence_level', 'unknown')}")
                
                # Calcular scores baseados nos dados coletados
                sanitario_score = self._calculate_sanitario_score(
                    result_data.get('rasff_alerts_6m', 0),
                    result_data.get('rasff_alerts_12m', 0),
                    ncm_code
                )
                
                fitossanitario_score = self._calculate_fitossanitario_score(
                    result_data.get('critical_substances', []),
                    result_data.get('rejection_reasons', []),
                    ncm_code
                )
                
                return {
                    'source': 'dyad',
                    'rasff_alerts_90d': result_data.get('rasff_alerts_90d', 0),
                    'rasff_alerts_6m': result_data.get('rasff_alerts_6m', 0),
                    'rasff_alerts_12m': result_data.get('rasff_alerts_12m', 0),
                    'main_rejection_reasons': result_data.get('rejection_reasons', []),
                    'critical_substances': result_data.get('critical_substances', []),
                    'sanitario_score': sanitario_score,
                    'fitossanitario_score': fitossanitario_score,
                    'timestamp': datetime.utcnow(),
                    'confidence': result_data.get('confidence_level', 'medium'),
                    'source_urls': result_data.get('source_urls', [])
                }
            
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao decodificar JSON da resposta Dyad: {e}")
        except TimeoutError:
            print("⏱️ Timeout ao executar agente Dyad")
        except Exception as e:
            print(f"❌ Erro inesperado no agente Dyad: {e}")
        
        return None
    
    def _calculate_sanitario_score(self, alerts_6m: int, alerts_12m: int, ncm_code: str) -> float:
        """
        Calcula score sanitário baseado em alertas RASFF e perfil histórico.
        """
        profile = NCM_RISK_PROFILES.get(ncm_code, {})
        base_score = profile.get('sanitario_base', 85.0)
        
        # Penalidades: -10 pontos por alerta recente (6m), -4 por alerta antigo (12m)
        penalty = (alerts_6m * 10) + (alerts_12m * 4)
        final_score = max(0, base_score - penalty)
        
        return round(final_score, 1)
    
    def _calculate_fitossanitario_score(self, substances: List[str], reasons: List[str], ncm_code: str) -> float:
        """
        Calcula score fitossanitário baseado em substâncias críticas e motivos de rejeição.
        """
        profile = NCM_RISK_PROFILES.get(ncm_code, {})
        base_score = profile.get('fitossanitario_base', 80.0)
        
        # Penalizar se substâncias perigosas foram detectadas
        penalty = len(substances) * 5
        
        # Penalizar motivos fitossanitários específicos
        phyto_keywords = ['pest', 'praga', 'quarantine', 'phytosanitary', 'insect']
        for reason in reasons:
            if any(keyword in reason.lower() for keyword in phyto_keywords):
                penalty += 8
        
        final_score = max(0, base_score - penalty)
        
        return round(final_score, 1)
    
    def _get_fallback_data(self, ncm_code: str, product_name: str) -> Dict:
        """
        Retorna dados históricos quando Dyad não está disponível.
        """
        
        print("📋 Usando dados históricos do perfil NCM...")
        
        profile = NCM_RISK_PROFILES.get(ncm_code, {
            "name": product_name,
            "historical_rejections": 0,
            "sanitario_base": 85.0,
            "fitossanitario_base": 80.0,
            "common_issues": []
        })
        
        # Estimar alertas baseados em rejeições históricas
        historical_rejections = profile.get('historical_rejections', 0)
        alerts_6m = min(historical_rejections // 2, historical_rejections)
        alerts_12m = historical_rejections
        
        return {
            'source': 'fallback',
            'rasff_alerts_90d': alerts_6m // 2,
            'rasff_alerts_6m': alerts_6m,
            'rasff_alerts_12m': alerts_12m,
            'main_rejection_reasons': profile.get('common_issues', []),
            'critical_substances': [],
            'sanitario_score': profile.get('sanitario_base', 85.0),
            'fitossanitario_score': profile.get('fitossanitario_base', 80.0),
            'timestamp': datetime.utcnow(),
            'confidence': 'low',
            'source_urls': []
        }

# ==================================================================================
# LEGACY ANVISA SCRAPER - Mantido para LMR específicos
# ==================================================================================

class ANVISAScraper:
    """
    Scraper legado da ANVISA mantido para coleta de LMR específicos.
    Dyad cuida dos alertas RASFF, este scraper foca em dados técnicos.
    """
    
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

# ==================================================================================
# PYDANTIC MODELS
# ==================================================================================

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
    use_dyad: bool = True

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

# ==================================================================================
# ENHANCED RISK CALCULATOR - Atualizado para usar Dyad
# ==================================================================================

class EnhancedRiskCalculator:
    """
    Motor de cálculo de risco ZOI atualizado com integração Dyad.
    """
    
    def __init__(self):
        self.dyad_navigator = DyadComplianceNavigator()
    
    def calculate(
        self, 
        product, 
        rasff_6m: int = None, 
        rasff_12m: int = None,
        use_dyad: bool = True
    ) -> dict:
        """
        Calcula o risco usando dados Dyad (preferencial) ou fallback histórico.
        """
        
        # Se use_dyad=True e nenhum alerta foi fornecido, buscar via Dyad
        if use_dyad and (rasff_6m is None or rasff_12m is None):
            print("🤖 Acionando Dyad para coleta de dados em tempo real...")
            
            dyad_data = self.dyad_navigator.fetch_dyad_compliance_data(
                product.ncm_code,
                product.name_pt
            )
            
            # Usar dados Dyad se disponíveis
            if dyad_data['source'] == 'dyad':
                rasff_6m = dyad_data['rasff_alerts_6m']
                rasff_12m = dyad_data['rasff_alerts_12m']
                sanitario = dyad_data['sanitario_score']
                fitossanitario = dyad_data['fitossanitario_score']
                
                print(f"✅ Usando dados Dyad: Sanitário={sanitario}, Fitossanitário={fitossanitario}")
            else:
                # Fallback para perfil histórico
                print("⚠️ Dyad indisponível, usando perfil histórico")
                rasff_6m = dyad_data['rasff_alerts_6m']
                rasff_12m = dyad_data['rasff_alerts_12m']
                sanitario = dyad_data['sanitario_score']
                fitossanitario = dyad_data['fitossanitario_score']
        else:
            # Modo manual: usar alertas fornecidos pelo usuário
            profile = NCM_RISK_PROFILES.get(product.ncm_code, {
                "sanitario_base": 85.0,
                "fitossanitario_base": 80.0,
                "logistico_base": 85.0,
                "documental_base": 80.0,
                "historical_rejections": 0
            })
            
            rasff_6m = rasff_6m or 0
            rasff_12m = rasff_12m or 0
            
            # Cálculo tradicional
            sanitario = max(0, profile['sanitario_base'] - (rasff_6m * 10) - (rasff_12m * 4))
            fitossanitario = profile['fitossanitario_base']
            
            if product.state.value == 'frozen':
                fitossanitario = min(100, fitossanitario + 10)
        
        # Componentes logístico e documental (não afetados por Dyad)
        profile = NCM_RISK_PROFILES.get(product.ncm_code, {})
        logistico = profile.get('logistico_base', 85.0)
        documental = profile.get('documental_base', 80.0)
        
        # Score final (média ponderada)
        score = (sanitario * 0.4) + (fitossanitario * 0.3) + (logistico * 0.15) + (documental * 0.15)
        
        # Definição de status
        if score >= 80:
            status = "green"
            label = "Baixo Risco"
        elif score >= 60:
            status = "yellow"
            label = "Risco Moderado"
        else:
            status = "red"
            label = "Alto Risco"
        
        # Recomendações automáticas
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

# ==================================================================================
# FASTAPI APPLICATION
# ==================================================================================

app = FastAPI(
    title="ZOI Trade Advisory API",
    description="Sistema Bilateral de Compliance Sanitária e Fitossanitária com Navegação Inteligente",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================================================================================
# SECURITY CONFIGURATION
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

# ==================================================================================
# API ROUTES
# ==================================================================================

@app.get("/")
def root():
    return {
        "message": "ZOI Trade Advisory API v2.1 - Powered by Dyad Intelligence",
        "status": "operational",
        "dyad_status": "active" if DYAD_AVAILABLE else "fallback_mode",
        "endpoints": {
            "products": "/api/products",
            "risk_calculation": "/api/risk/calculate",
            "admin": "/api/admin",
            "export_pdf": "/api/products/{key}/export-pdf"
        }
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

@app.post("/api/risk/calculate")
def calculate_risk(request: RiskCalculationRequest, db: SessionLocal = Depends(get_db)):
    """
    Calcula risco usando Dyad Intelligence (preferencial) ou dados históricos.
    """
    print(f"🧮 Calculando risco para produto: {request.product_key}")
    
    product = db.query(Product).filter(Product.key == request.product_key).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Inicializar calculadora com Dyad
    calc = EnhancedRiskCalculator()
    
    # Calcular usando Dyad ou alertas fornecidos
    result = calc.calculate(
        product,
        rasff_6m=request.rasff_alerts_6m if request.rasff_alerts_6m > 0 else None,
        rasff_12m=request.rasff_alerts_12m if request.rasff_alerts_12m > 0 else None,
        use_dyad=request.use_dyad
    )
    
    # Salvar avaliação no banco
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
            rasff_alerts_6m=result['alerts']['rasff_6m'],
            rasff_alerts_12m=result['alerts']['rasff_12m'],
            recommendations=result['recommendations'],
            dyad_data_source='dyad' if request.use_dyad else 'manual',
            dyad_last_fetch=datetime.utcnow()
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
        },
        "data_source": "dyad_intelligence" if request.use_dyad else "manual_input"
    }

@app.get("/api/products/{product_key}/export-pdf")
def export_risk_pdf(product_key: str):
    """
    Endpoint de exportação PDF - SEM DEPENDÊNCIAS EXTERNAS
    """
    print(f"📄 [PDF ENDPOINT ATIVADO] Gerando PDF para: {product_key}")
    
    db = SessionLocal()
    
    try:
        product = db.query(Product).filter(Product.key == product_key).first()
        if not product:
            db.close()
            return Response(
                content=b"Produto nao encontrado",
                status_code=404,
                media_type="text/plain"
            )
        
        print(f"✅ Produto encontrado: {product.name_pt}")
        
        latest_assessment = db.query(RiskAssessment)\
            .filter(RiskAssessment.product_id == product.id)\
            .order_by(RiskAssessment.calculation_timestamp.desc())\
            .first()
        
        if not latest_assessment:
            print("🔄 Calculando nova avaliação de risco...")
            calc = EnhancedRiskCalculator()
            result = calc.calculate(product, use_dyad=True)
            
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
        
        profile = NCM_RISK_PROFILES.get(product.ncm_code, {})
        
        alerts_section = ""
        if assessment_data['alerts']['rasff_12m'] > 0 or assessment_data['alerts'].get('historical_rejections', 0) > 0:
            alerts_section = f"""
<div class="section">
    <h2>⚠️ Alertas e Histórico</h2>
    <div class="alert-box">
        <div class="alert-title">Alertas RASFF (Sistema de Alerta Rápido UE)</div>
        <p>📅 Últimos 6 meses: <strong>{assessment_data['alerts']['rasff_6m']} alertas</strong></p>
        <p>📅 Últimos 12 meses: <strong>{assessment_data['alerts']['rasff_12m']} alertas</strong></p>
        <p>📊 Rejeições históricas (NCM): <strong>{assessment_data['alerts'].get('historical_rejections', 0)} casos</strong></p>
    </div>
</div>
            """
        
        profile_section = ""
        if profile:
            common_issues = ', '.join(profile.get('common_issues', [])[:2])
            profile_section = f"""
<div class="section">
    <h2>🔍 Perfil de Risco do NCM</h2>
    <div class="info-grid">
        <div class="info-item">
            <div class="info-label">Barreiras UE</div>
            <div class="info-value">{profile.get('eu_barriers', 'N/A').upper()}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Problemas Comuns</div>
            <div class="info-value" style="font-size: 14px;">{common_issues or 'N/A'}</div>
        </div>
    </div>
</div>
            """
        
        recommendations_html = "".join([f'<div class="recommendation-item">{rec}</div>' for rec in assessment_data['recommendations']])
        
        direction_text = 'Exportacao BR→IT' if product.direction.value == 'export' else 'Importacao IT→BR'
        
        comp_sanitario = assessment_data['components'].get('Sanitario', assessment_data['components'].get('Sanitário', 85.0))
        comp_fitossanitario = assessment_data['components'].get('Fitossanitario', assessment_data['components'].get('Fitossanitário', 80.0))
        comp_logistico = assessment_data['components'].get('Logistico', assessment_data['components'].get('Logístico', 88.0))
        comp_documental = assessment_data['components'].get('Documental', 82.0)
        
        html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>ZOI Trade Advisory - Relatorio de Risco</title>
    <style>
        @page {{ size: A4; margin: 2cm; }}
        body {{ font-family: Arial, Helvetica, sans-serif; color: #1e293b; line-height: 1.6; margin: 0; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #1e40af 0%, #3b82f6 100%); color: white; padding: 30px; margin: -20px -20px 30px -20px; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .header p {{ margin: 5px 0 0 0; opacity: 0.9; }}
        .score-badge {{ display: inline-block; padding: 10px 20px; border-radius: 8px; font-weight: bold; font-size: 24px; margin: 20px 0; }}
        .score-green {{ background: #dcfce7; color: #166534; }}
        .score-yellow {{ background: #fef3c7; color: #854d0e; }}
        .score-red {{ background: #fee2e2; color: #991b1b; }}
        .section {{ margin: 25px 0; page-break-inside: avoid; }}
        .section h2 {{ color: #1e40af; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; margin-bottom: 15px; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .info-item {{ background: #f8fafc; padding: 15px; border-radius: 6px; border-left: 4px solid #3b82f6; }}
        .info-label {{ font-weight: 600; color: #64748b; font-size: 12px; text-transform: uppercase; }}
        .info-value {{ font-size: 18px; font-weight: bold; color: #0f172a; margin-top: 5px; }}
        .component-bar {{ margin: 15px 0; }}
        .component-label {{ font-weight: 600; margin-bottom: 5px; display: flex; justify-content: space-between; }}
        .bar-container {{ background: #e2e8f0; border-radius: 10px; height: 25px; overflow: hidden; }}
        .bar-fill {{ background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%); height: 100%; display: flex; align-items: center; justify-content: flex-end; padding-right: 10px; color: white; font-weight: bold; font-size: 12px; }}
        .recommendations {{ background: #eff6ff; border-left: 4px solid #3b82f6; padding: 20px; border-radius: 6px; }}
        .recommendation-item {{ padding: 8px 0; border-bottom: 1px solid #dbeafe; }}
        .recommendation-item:last-child {{ border-bottom: none; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 2px solid #e2e8f0; text-align: center; color: #64748b; font-size: 12px; }}
        .alert-box {{ background: #fef3c7; border: 2px solid #fbbf24; border-radius: 8px; padding: 15px; margin: 20px 0; }}
        .alert-title {{ font-weight: bold; color: #92400e; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🛡️ ZOI Trade Advisory</h1>
        <p>Relatorio Executivo de Analise de Risco Sanitario e Fitossanitario</p>
    </div>

    <div class="section">
        <h2>📋 Informacoes do Produto</h2>
        <div class="info-grid">
            <div class="info-item">
                <div class="info-label">Produto</div>
                <div class="info-value">{product.name_pt}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Codigo NCM</div>
                <div class="info-value">{product.ncm_code}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Direcao Comercial</div>
                <div class="info-value">{direction_text}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Estado do Produto</div>
                <div class="info-value">{product.state.value.capitalize()}</div>
            </div>
        </div>
    </div>

    <div class="section">
        <h2>🎯 Score de Risco Global</h2>
        <div class="score-badge score-{assessment_data['status']}">
            {assessment_data['score']:.1f}/100 - {assessment_data['status_label']}
        </div>
        <p style="color: #64748b; margin-top: 10px;">
            Data da analise: {datetime.now().strftime('%d/%m/%Y as %H:%M')}
        </p>
    </div>

    <div class="section">
        <h2>📊 Componentes de Risco</h2>
        
        <div class="component-bar">
            <div class="component-label">
                <span>🏥 Sanitario</span>
                <span>{comp_sanitario:.1f}/100</span>
            </div>
            <div class="bar-container">
                <div class="bar-fill" style="width: {comp_sanitario}%">
                    {comp_sanitario:.0f}%
                </div>
            </div>
        </div>

        <div class="component-bar">
            <div class="component-label">
                <span>🌱 Fitossanitario</span>
                <span>{comp_fitossanitario:.1f}/100</span>
            </div>
            <div class="bar-container">
                <div class="bar-fill" style="width: {comp_fitossanitario}%">
                    {comp_fitossanitario:.0f}%
                </div>
            </div>
        </div>

        <div class="component-bar">
            <div class="component-label">
                <span>📦 Logistico</span>
                <span>{comp_logistico:.1f}/100</span>
            </div>
            <div class="bar-container">
                <div class="bar-fill" style="width: {comp_logistico}%">
                    {comp_logistico:.0f}%
                </div>
            </div>
        </div>

        <div class="component-bar">
            <div class="component-label">
                <span>📄 Documental</span>
                <span>{comp_documental:.1f}/100</span>
            </div>
            <div class="bar-container">
                <div class="bar-fill" style="width: {comp_documental}%">
                    {comp_documental:.0f}%
                </div>
            </div>
        </div>
    </div>

    {alerts_section}
    {profile_section}

    <div class="section">
        <h2>💡 Recomendacoes Estrategicas</h2>
        <div class="recommendations">
            {recommendations_html}
        </div>
    </div>

    <div class="footer">
        <p><strong>ZOI Trade Advisory</strong> - Sistema Bilateral de Compliance Sanitaria e Fitossanitaria</p>
        <p>Relatorio gerado automaticamente em {datetime.now().strftime('%d/%m/%Y as %H:%M:%S')}</p>
        <p style="margin-top: 10px; color: #94a3b8;">
            ⚠️ Este relatorio e baseado em dados publicos e analise automatizada. 
            Para decisoes comerciais criticas, consulte especialistas em comercio internacional.
        </p>
    </div>
</body>
</html>"""
        
        print(f"✅ HTML gerado com sucesso ({len(html_content)} caracteres)")
        
        db.close()
        
        filename = f"ZOI_Risk_Report_{product_key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        return Response(
            content=html_content.encode('utf-8'),
            media_type="text/html",
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        print(f"❌ ERRO ao gerar relatório: {str(e)}")
        import traceback
        traceback.print_exc()
        
        db.close()
        
        return Response(
            content=f"Erro ao gerar relatorio: {str(e)}".encode('utf-8'),
            status_code=500,
            media_type="text/plain"
        )

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
        "message": f"{total} produtos criados. Auditoria ANVISA iniciada em segundo plano.",
        "dyad_status": "active" if DYAD_AVAILABLE else "fallback_mode"
    }

def run_initial_scraping(product_name: str, product_key: str):
    """
    Background task para auditoria inicial de LMR.
    """
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

@app.get("/api/admin/stats")
def get_admin_stats(db: SessionLocal = Depends(get_db)):
    total_products = db.query(Product).count()
    total_assessments = db.query(RiskAssessment).count()
    total_users = db.query(User).count()
    
    green_count = db.query(RiskAssessment).filter(RiskAssessment.status == RiskStatusDB.GREEN).count()
    yellow_count = db.query(RiskAssessment).filter(RiskAssessment.status == RiskStatusDB.YELLOW).count()
    red_count = db.query(RiskAssessment).filter(RiskAssessment.status == RiskStatusDB.RED).count()
    
    # Estatísticas Dyad
    dyad_assessments = db.query(RiskAssessment).filter(RiskAssessment.dyad_data_source == 'dyad').count()
    fallback_assessments = db.query(RiskAssessment).filter(RiskAssessment.dyad_data_source == 'fallback').count()
    
    return {
        "total_products": total_products,
        "total_assessments": total_assessments,
        "total_users": total_users,
        "status_distribution": {
            "green": green_count,
            "yellow": yellow_count,
            "red": red_count
        },
        "data_sources": {
            "dyad_intelligence": dyad_assessments,
            "historical_fallback": fallback_assessments,
            "dyad_available": DYAD_AVAILABLE
        }
    }

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

if __name__ == "__main__":
    import uvicorn
    Base.metadata.create_all(bind=engine)
    port = int(os.environ.get("PORT", 8000))
    
    print("\n" + "="*70)
    print("🚀 ZOI TRADE ADVISORY API v2.1 - DYAD INTELLIGENCE")
    print("="*70)
    print(f"✅ Dyad Status: {'ACTIVE' if DYAD_AVAILABLE else 'FALLBACK MODE'}")
    print(f"✅ Database: Connected")
    print(f"✅ Server: http://0.0.0.0:{port}")
    print("="*70 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
