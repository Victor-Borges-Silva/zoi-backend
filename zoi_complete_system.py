"""
ZOI Trade Advisory - Complete Production System
Version 2.0 - Full Stack Implementation

Architecture:
├── Data Layer (Scrapers + Database)
├── Business Logic (Risk Engine + Validators)
├── API Layer (FastAPI REST)
├── Notification System (Email + Webhooks)
└── Admin Dashboard (Management Interface)

Dependencies:
pip install fastapi uvicorn sqlalchemy psycopg2-binary alembic
pip install selenium beautifulsoup4 requests pandas
pip install pydantic python-multipart python-jose passlib
pip install celery redis APScheduler sendgrid
"""

# ============================================================================
# 1. SCRAPER ANVISA (LMRs Brasileiros)
# ============================================================================

import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import json
from pathlib import Path
import time


class ANVISAScraper:
    """
    Scraper para dados ANVISA (LMRs brasileiros)
    Fonte: https://www.gov.br/anvisa/pt-br/assuntos/agrotoxicos
    """
    
    BASE_URL = "https://www.gov.br/anvisa/pt-br"
    MONOGRAFIA_URL = f"{BASE_URL}/assuntos/agrotoxicos/monografia"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_lmr_for_substance(self, substance: str, crop: str) -> Optional[Dict]:
        """
        Busca LMR brasileiro para substância + cultura
        
        Args:
            substance: Nome da substância (ex: 'Glifosato')
            crop: Nome da cultura (ex: 'Soja')
        
        Returns:
            {'substance': str, 'crop': str, 'lmr_mg_kg': float, 'source': str}
        """
        
        try:
            # Buscar página da monografia
            search_url = f"{self.MONOGRAFIA_URL}?ingrediente={substance.lower()}"
            response = self.session.get(search_url, timeout=10)
            
            if response.status_code != 200:
                print(f"[ANVISA] Erro ao acessar {substance}: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extrair tabela de LMRs
            lmr_table = soup.find('table', {'class': 'lmr-table'})
            
            if not lmr_table:
                # Tentar estrutura alternativa
                lmr_table = soup.find('table', string=re.compile('Limite Máximo'))
            
            if lmr_table:
                rows = lmr_table.find_all('tr')
                
                for row in rows:
                    cols = row.find_all('td')
                    
                    if len(cols) >= 2:
                        crop_cell = cols[0].text.strip().lower()
                        
                        if crop.lower() in crop_cell:
                            lmr_text = cols[1].text.strip()
                            lmr_value = self._extract_number(lmr_text)
                            
                            if lmr_value is not None:
                                return {
                                    'substance': substance,
                                    'crop': crop,
                                    'lmr_mg_kg': lmr_value,
                                    'source': 'ANVISA',
                                    'url': search_url
                                }
            
            # Fallback: Usar dados tabelados conhecidos
            return self._get_fallback_lmr(substance, crop)
            
        except Exception as e:
            print(f"[ANVISA] Erro ao processar {substance}: {e}")
            return self._get_fallback_lmr(substance, crop)
    
    def _extract_number(self, text: str) -> Optional[float]:
        """Extrai número do texto"""
        match = re.search(r'(\d+\.?\d*)', text.replace(',', '.'))
        return float(match.group(1)) if match else None
    
    def _get_fallback_lmr(self, substance: str, crop: str) -> Dict:
        """
        Dados de fallback baseados em tabelas ANVISA conhecidas
        TODO: Expandir esta base de dados
        """
        
        fallback_data = {
            ('Glifosato', 'Soja'): 10.0,
            ('Glifosato', 'Café'): 1.0,
            ('Carbendazim', 'Laranja'): 2.0,
            ('Carbendazim', 'Café'): 0.1,
            ('Clorpirifós', 'Soja'): 0.5,
            ('Tiabendazol', 'Laranja'): 5.0,
        }
        
        lmr = fallback_data.get((substance, crop), 1.0)
        
        return {
            'substance': substance,
            'crop': crop,
            'lmr_mg_kg': lmr,
            'source': 'ANVISA_FALLBACK',
            'url': self.MONOGRAFIA_URL
        }
    
    def batch_collect(self, substances: List[str], crops: List[str]) -> List[Dict]:
        """Coleta em lote de múltiplas substâncias × culturas"""
        
        results = []
        
        for substance in substances:
            for crop in crops:
                print(f"[ANVISA] Buscando {substance} × {crop}...")
                result = self.get_lmr_for_substance(substance, crop)
                
                if result:
                    results.append(result)
                
                time.sleep(1)  # Rate limiting
        
        return results


# ============================================================================
# 2. DATABASE SCHEMA (SQLAlchemy + PostgreSQL)
# ============================================================================

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum

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
    """Tabela de produtos"""
    __tablename__ = 'products'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    name_pt = Column(String(200), nullable=False)
    name_it = Column(String(200), nullable=False)
    name_en = Column(String(200))
    
    # Códigos aduaneiros
    ncm_code = Column(String(8), nullable=False)
    hs_code = Column(String(6), nullable=False)
    taric_code = Column(String(10))
    
    # Características
    direction = Column(SQLEnum(TradeDirectionDB), nullable=False)
    state = Column(SQLEnum(ProductStateDB), nullable=False)
    category = Column(String(50))
    
    # Parâmetros logísticos
    shelf_life_days = Column(Integer)
    transport_days_avg = Column(Integer)
    temperature_min_c = Column(Float)
    temperature_max_c = Column(Float)
    
    # Certificações
    requires_phytosanitary_cert = Column(Boolean, default=True)
    requires_health_cert = Column(Boolean, default=False)
    requires_origin_cert = Column(Boolean, default=True)
    
    # Metadados
    critical_substances = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    risk_assessments = relationship("RiskAssessment", back_populates="product")
    lmr_data = relationship("LMRData", back_populates="product")


class RiskAssessment(Base):
    """Tabela de avaliações de risco"""
    __tablename__ = 'risk_assessments'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    
    # Scores
    final_score = Column(Float, nullable=False)
    status = Column(SQLEnum(RiskStatusDB), nullable=False)
    
    # Componentes
    rasff_score = Column(Float)
    lmr_score = Column(Float)
    phyto_score = Column(Float)
    logistic_score = Column(Float)
    penalty = Column(Float)
    
    # Dados de entrada
    rasff_alerts_6m = Column(Integer)
    rasff_alerts_12m = Column(Integer)
    
    # Metadados
    calculation_timestamp = Column(DateTime, default=datetime.utcnow)
    recommendations = Column(JSON)
    
    # Relacionamentos
    product = relationship("Product", back_populates="risk_assessments")


class LMRData(Base):
    """Tabela de dados de LMR (Limite Máximo de Resíduos)"""
    __tablename__ = 'lmr_data'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    
    substance = Column(String(200), nullable=False)
    source_lmr = Column(Float)  # LMR do país de origem
    dest_lmr = Column(Float)    # LMR do país de destino
    detection_rate = Column(Float)
    
    source_authority = Column(String(50))  # ANVISA, EFSA, etc.
    last_updated = Column(DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    product = relationship("Product", back_populates="lmr_data")


class NotificationLog(Base):
    """Log de notificações enviadas"""
    __tablename__ = 'notification_logs'
    
    id = Column(Integer, primary_key=True)
    user_email = Column(String(200), nullable=False)
    product_key = Column(String(100), nullable=False)
    risk_score = Column(Float)
    notification_type = Column(String(50))  # email, webhook, sms
    sent_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=True)
    error_message = Column(String(500))


class User(Base):
    """Tabela de usuários"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    full_name = Column(String(200))
    company = Column(String(200))
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Preferências de notificação
    notification_threshold = Column(Float, default=65.0)
    email_notifications = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# Database connection
DATABASE_URL = "postgresql://zoi_user:IN3LI5N6OshhlVIDetxmCXhX01es3nK8@dpg-d5pkoeer433s73ddm970-a/zoi_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_database():
    """Inicializa banco de dados"""
    Base.metadata.create_all(bind=engine)
    print("[DB] ✓ Banco de dados inicializado")


# ============================================================================
# 3. FASTAPI REST API
# ============================================================================

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import timedelta

# Pydantic Models
class ProductResponse(BaseModel):
    id: int
    key: str
    name_pt: str
    name_it: str
    ncm_code: str
    direction: str
    state: str
    shelf_life_days: int
    
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


# FastAPI App
app = FastAPI(
    title="ZOI Trade Advisory API",
    description="Sistema Bilateral de Compliance Sanitária e Fitossanitária",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Produção: especificar domínios
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Helper Functions
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


# API Endpoints
@app.get("/")
def root():  
    return {
        "message": "ZOI Trade Advisory API v2.0",
        "status": "operational",
        "endpoints": {
            "products": "/api/products",
            "risk_calculation": "/api/calculate-risk",
            "admin": "/api/admin"
        }
    }
# ============================================================================
# ROTA DE SEED - POPULAR BANCO DE DADOS
# ============================================================================
@app.get("/api/admin/seed-database")
def seed_database():
    from sqlalchemy.orm import Session
    
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    
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
            {"key": "limao_siciliano", "name": "Limão Siciliano", "ncm": "08055000", "dir": "import", "state": "ambient"}
        ]
        
        for item in products_list:
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
        
        session.commit()
        total = session.query(Product).count()
        
    return {"status": "success", "total": total}
 
@app.get("/api/products")
def get_products():
    from sqlalchemy.orm import Session
    with Session(engine) as session:
        products = session.query(Product).all()
        return products
    
    """Lista produtos com filtros opcionais"""
    
    query = db.query(Product)
    
    if direction:
        query = query.filter(Product.direction == direction)
    
    if state:
        query = query.filter(Product.state == state)
    
    products = query.all()
    
    return products


@app.get("/api/products/{product_key}", response_model=ProductResponse)
def get_product(product_key: str, db: SessionLocal = Depends(get_db)):
    """Retorna detalhes de um produto específico"""
    
    product = db.query(Product).filter(Product.key == product_key).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    return product


@app.post("/api/calculate-risk", response_model=RiskCalculationResponse)
def calculate_risk(
    request: RiskCalculationRequest,
    background_tasks: BackgroundTasks,
    db: SessionLocal = Depends(get_db)
):
    """
    Calcula Risk Score para um produto
    """
    
    # Buscar produto
    product = db.query(Product).filter(Product.key == request.product_key).first()
    
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Importar motor de risco (assumindo que está no mesmo arquivo)
    from zoi_bilateral_system import SentinelScore2Engine, ProductSpec, TradeDirection, ProductState
    
    # Converter para ProductSpec
    product_spec = ProductSpec(
        name_pt=product.name_pt,
        name_it=product.name_it,
        name_en=product.name_en or "",
        ncm_code=product.ncm_code,
        hs_code=product.hs_code,
        taric_code=product.taric_code,
        state=ProductState(product.state.value),
        shelf_life_days=product.shelf_life_days,
        transport_days_avg=product.transport_days_avg,
        temperature_min_c=product.temperature_min_c,
        temperature_max_c=product.temperature_max_c,
        requires_phytosanitary_cert=product.requires_phytosanitary_cert,
        requires_health_cert=product.requires_health_cert,
        critical_substances=product.critical_substances or []
    )
    
    # Calcular risco
    engine = SentinelScore2Engine(TradeDirection(product.direction.value))
    
    result = engine.calculate_risk_score(
        product=product_spec,
        rasff_data={
            'alerts_6m': request.rasff_alerts_6m,
            'alerts_12m': request.rasff_alerts_12m
        },
        lmr_data=request.lmr_data,
        phyto_data={'alerts': request.phyto_alerts},
        transport_data={'days': request.transport_days or product.transport_days_avg}
    )
    
    # Salvar avaliação no banco
    assessment = RiskAssessment(
        product_id=product.id,
        final_score=result['score'],
        status=RiskStatusDB(result['status']),
        rasff_score=result['components']['rasff_score'],
        lmr_score=result['components']['lmr_score'],
        phyto_score=result['components']['phyto_score'],
        logistic_score=result['components']['logistic_score'],
        penalty=result['components']['penalty'],
        rasff_alerts_6m=request.rasff_alerts_6m,
        rasff_alerts_12m=request.rasff_alerts_12m,
        recommendations=result['recommendations']
    )
    
    db.add(assessment)
    db.commit()
    
    # Enviar notificações em background se score > threshold
    if result['score'] > 65:
        background_tasks.add_task(
            send_risk_notifications,
            product_key=request.product_key,
            score=result['score'],
            status=result['status']
        )
    
    return result


@app.post("/api/users", status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate, db: SessionLocal = Depends(get_db)):
    """Cria novo usuário"""
    
    # Verificar se email já existe
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Criar usuário
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
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: SessionLocal = Depends(get_db)
):
    """Login endpoint"""
    
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
    """Estatísticas do sistema (admin apenas)"""
    
    total_products = db.query(Product).count()
    total_assessments = db.query(RiskAssessment).count()
    total_users = db.query(User).count()
    
    # Distribuição de status
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


# ============================================================================
# 4. NOTIFICATION SYSTEM
# ============================================================================

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class NotificationService:
    """Serviço de notificações (Email + Webhooks)"""
    
    # Configuração SMTP (usar variáveis de ambiente em produção)
    SMTP_SERVER = "smtp.sendgrid.net"
    SMTP_PORT = 587
    SMTP_USER = "apikey"
    SMTP_PASSWORD = "your-sendgrid-api-key"
    FROM_EMAIL = "alerts@zoi-trade.com"
    
    @classmethod
    def send_email(cls, to_email: str, subject: str, html_content: str) -> bool:
        """Envia email via SMTP"""
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = cls.FROM_EMAIL
            msg['To'] = to_email
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(cls.SMTP_SERVER, cls.SMTP_PORT) as server:
                server.starttls()
                server.login(cls.SMTP_USER, cls.SMTP_PASSWORD)
                server.send_message(msg)
            
            print(f"[EMAIL] ✓ Enviado para {to_email}")
            return True
            
        except Exception as e:
            print(f"[EMAIL] ✗ Erro ao enviar para {to_email}: {e}")
            return False
    
    @classmethod
    def send_risk_alert(cls, user_email: str, product_name: str, score: float, status: str):
        """Envia alerta de risco alto"""
        
        status_emoji = "🛑" if status == "red" else "⚠️"
        
        subject = f"{status_emoji} ZOI Alert: {product_name} - Risk Score {score}"
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #1e40af;">ZOI Trade Advisory Alert</h2>
                
                <div style="background: #fee2e2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">{status_emoji} High Risk Detected</h3>
                    <p><strong>Product:</strong> {product_name}</p>
                    <p><strong>Risk Score:</strong> {score}/100</p>
                    <p><strong>Status:</strong> {status.upper()}</p>
                </div>
                
                <p>Our system has detected elevated compliance risks for this shipment.</p>
                
                <p><strong>Recommended Actions:</strong></p>
                <ul>
                    <li>Review laboratory analysis reports</li>
                    <li>Verify certification documents</li>
                    <li>Consider alternative suppliers or routes</li>
                </ul>
                
                <p style="margin-top: 30px; color: #6b7280;">
                    <small>This is an automated alert from ZOI Sentinel System</small>
                </p>
            </div>
        </body>
        </html>
        """
        
        return cls.send_email(user_email, subject, html_content)


def send_risk_notifications(product_key: str, score: float, status: str):
    """
    Função para enviar notificações (chamada em background)
    """
    
    db = SessionLocal()
    
    try:
        # Buscar produto
        product = db.query(Product).filter(Product.key == product_key).first()
        
        if not product:
            return
        
        # Buscar usuários que querem notificações
        users = db.query(User).filter(
            User.email_notifications == True,
            User.notification_threshold <= score
        ).all()
        
        for user in users:
            # Enviar email
            success = NotificationService.send_risk_alert(
                user_email=user.email,
                product_name=product.name_pt,
                score=score,
                status=status
            )
            
            # Registrar log
            log = NotificationLog(
                user_email=user.email,
                product_key=product_key,
                risk_score=score,
                notification_type="email",
                success=success,
                error_message=None if success else "SMTP error"
            )
            db.add(log)
        
        db.commit()
        
    finally:
        db.close()


# ============================================================================
# 5. ADMIN DASHBOARD (CLI + Web Interface Básica)
# ============================================================================

import click


@click.group()
def cli():
    """ZOI Admin CLI"""
    pass


@cli.command()
def init_db():
    """Inicializa banco de dados"""
    init_database()
    click.echo("✓ Database initialized")


@cli.command()
@click.option('--direction', type=click.Choice(['export', 'import']))
def seed_products(direction):
    """Popula banco com produtos padrão"""
    
    from zoi_bilateral_system import ProductDatabase, TradeDirection
    
    db = SessionLocal()
    
    trade_dir = TradeDirection.BR_TO_IT if direction == 'export' else TradeDirection.IT_TO_BR
    products_dict = ProductDatabase.get_all_products(trade_dir)
    
    for key, spec in products_dict.items():
        existing = db.query(Product).filter(Product.key == key).first()
        
        if existing:
            click.echo(f"⊘ {key} já existe")
            continue
        
        product = Product(
            key=key,
            name_pt=spec.name_pt,
            name_it=spec.name_it,
            name_en=spec.name_en,
            ncm_code=spec.ncm_code,
            hs_code=spec.hs_code,
            taric_code=spec.taric_code,
            direction=TradeDirectionDB(direction),
            state=ProductStateDB(spec.state.value),
            shelf_life_days=spec.shelf_life_days,
            transport_days_avg=spec.transport_days_avg,
            temperature_min_c=spec.temperature_min_c,
            temperature_max_c=spec.temperature_max_c,
            requires_phytosanitary_cert=spec.requires_phytosanitary_cert,
            requires_health_cert=spec.requires_health_cert,
            critical_substances=spec.critical_substances
        )
        
        db.add(product)
        click.echo(f"✓ {key} adicionado")
    
    db.commit()
    db.close()
    
    click.echo(f"\n✓ {len(products_dict)} produtos importados")


@cli.command()
def collect_anvisa_data():
    """Coleta dados de LMR da ANVISA"""
    
    scraper = ANVISAScraper()
    
    substances = ['Glifosato', 'Carbendazim', 'Clorpirifós', 'Tiabendazol']
    crops = ['Soja', 'Café', 'Laranja', 'Manga']
    
    click.echo("[ANVISA] Iniciando coleta...")
    
    results = scraper.batch_collect(substances, crops)
    
    # Salvar em arquivo JSON
    output_path = Path("data/anvisa_lmr_data.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    click.echo(f"✓ {len(results)} registros coletados")
    click.echo(f"✓ Dados salvos em {output_path}")


@cli.command()
@click.option('--email', prompt=True)
@click.option('--password', prompt=True, hide_input=True)
@click.option('--name', prompt=True)
def create_admin(email, password, name):
    """Cria usuário administrador"""
    
    db = SessionLocal()
    
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        click.echo("✗ Email já cadastrado")
        return
    
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        full_name=name,
        is_admin=True,
        is_active=True
    )
    
    db.add(user)
    db.commit()
    
    click.echo(f"✓ Admin criado: {email}")
    db.close()


@cli.command()
def stats():
    """Exibe estatísticas do sistema"""
    
    db = SessionLocal()
    
    total_products = db.query(Product).count()
    total_assessments = db.query(RiskAssessment).count()
    total_users = db.query(User).count()
    
    # Últimas avaliações
    recent = db.query(RiskAssessment).order_by(RiskAssessment.calculation_timestamp.desc()).limit(5).all()
    
    click.echo("\n" + "="*60)
    click.echo("ZOI SYSTEM STATISTICS")
    click.echo("="*60)
    click.echo(f"\nProducts: {total_products}")
    click.echo(f"Risk Assessments: {total_assessments}")
    click.echo(f"Registered Users: {total_users}")
    
    if recent:
        click.echo("\n" + "-"*60)
        click.echo("RECENT ASSESSMENTS")
        click.echo("-"*60)
        
        for assessment in recent:
            product = db.query(Product).filter(Product.id == assessment.product_id).first()
            click.echo(f"\n{assessment.calculation_timestamp.strftime('%Y-%m-%d %H:%M')}")
            click.echo(f"  Product: {product.name_pt if product else 'Unknown'}")
            click.echo(f"  Score: {assessment.final_score} ({assessment.status.value})")
    
    click.echo("\n" + "="*60 + "\n")
    db.close()


# ============================================================================
# 6. SCHEDULED TASKS (Data Collection Automation)
# ============================================================================

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class ScheduledTasks:
    """Tarefas agendadas para coleta automática de dados"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler()
    
    def start(self):
        """Inicia scheduler"""
        
        # Coletar RASFF toda segunda-feira às 8h
        self.scheduler.add_job(
            self.collect_rasff_data,
            CronTrigger(day_of_week='mon', hour=8, minute=0),
            id='rasff_collection',
            name='RASFF Data Collection'
        )
        
        # Coletar ANVISA toda sexta-feira às 18h
        self.scheduler.add_job(
            self.collect_anvisa_data,
            CronTrigger(day_of_week='fri', hour=18, minute=0),
            id='anvisa_collection',
            name='ANVISA Data Collection'
        )
        
        # Recalcular riscos todo dia às 6h
        self.scheduler.add_job(
            self.recalculate_all_risks,
            CronTrigger(hour=6, minute=0),
            id='risk_recalculation',
            name='Daily Risk Recalculation'
        )
        
        self.scheduler.start()
        print("[SCHEDULER] ✓ Tarefas agendadas iniciadas")
    
    @staticmethod
    def collect_rasff_data():
        """Coleta dados RASFF automaticamente"""
        print("[SCHEDULER] Iniciando coleta RASFF...")
        
        try:
            from zoi_collector import RASFFScraper, BrowserManager
            
            driver = BrowserManager.create_driver(headless=True)
            scraper = RASFFScraper(driver)
            
            alerts = scraper.search_brazil_alerts(days_back=30)
            
            # Salvar em arquivo
            output_path = Path("data/scheduled/rasff_alerts.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'collected_at': datetime.utcnow().isoformat(),
                    'alerts': alerts
                }, f, indent=2, ensure_ascii=False)
            
            driver.quit()
            
            print(f"[SCHEDULER] ✓ {len(alerts)} alertas RASFF coletados")
            
        except Exception as e:
            print(f"[SCHEDULER] ✗ Erro na coleta RASFF: {e}")
    
    @staticmethod
    def collect_anvisa_data():
        """Coleta dados ANVISA automaticamente"""
        print("[SCHEDULER] Iniciando coleta ANVISA...")
        
        try:
            scraper = ANVISAScraper()
            
            substances = ['Glifosato', 'Carbendazim', 'Clorpirifós']
            crops = ['Soja', 'Café', 'Laranja']
            
            results = scraper.batch_collect(substances, crops)
            
            # Salvar
            output_path = Path("data/scheduled/anvisa_lmr.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'collected_at': datetime.utcnow().isoformat(),
                    'lmr_data': results
                }, f, indent=2, ensure_ascii=False)
            
            print(f"[SCHEDULER] ✓ {len(results)} LMRs ANVISA coletados")
            
        except Exception as e:
            print(f"[SCHEDULER] ✗ Erro na coleta ANVISA: {e}")
    
    @staticmethod
    def recalculate_all_risks():
        """Recalcula riscos para todos os produtos"""
        print("[SCHEDULER] Recalculando riscos...")
        
        db = SessionLocal()
        
        try:
            products = db.query(Product).all()
            
            for product in products:
                # Buscar dados mais recentes
                rasff_file = Path("data/scheduled/rasff_alerts.json")
                
                if rasff_file.exists():
                    with open(rasff_file, 'r') as f:
                        rasff_data_full = json.load(f)
                    
                    # Filtrar alertas para este produto
                    product_alerts = [
                        a for a in rasff_data_full.get('alerts', [])
                        if product.name_pt.lower() in a.get('product', '').lower()
                    ]
                    
                    alerts_6m = len([a for a in product_alerts[:6]])
                    alerts_12m = len(product_alerts[:12])
                    
                    # Calcular risco (simplificado)
                    from zoi_bilateral_system import SentinelScore2Engine, ProductSpec, TradeDirection, ProductState
                    
                    product_spec = ProductSpec(
                        name_pt=product.name_pt,
                        name_it=product.name_it,
                        name_en=product.name_en or "",
                        ncm_code=product.ncm_code,
                        hs_code=product.hs_code,
                        taric_code=product.taric_code,
                        state=ProductState(product.state.value),
                        shelf_life_days=product.shelf_life_days,
                        transport_days_avg=product.transport_days_avg,
                        temperature_min_c=product.temperature_min_c,
                        temperature_max_c=product.temperature_max_c,
                        requires_phytosanitary_cert=product.requires_phytosanitary_cert,
                        requires_health_cert=product.requires_health_cert,
                        critical_substances=product.critical_substances or []
                    )
                    
                    engine = SentinelScore2Engine(TradeDirection(product.direction.value))
                    
                    result = engine.calculate_risk_score(
                        product=product_spec,
                        rasff_data={'alerts_6m': alerts_6m, 'alerts_12m': alerts_12m},
                        lmr_data=[],
                        phyto_data={'alerts': []},
                        transport_data={}
                    )
                    
                    # Salvar avaliação
                    assessment = RiskAssessment(
                        product_id=product.id,
                        final_score=result['score'],
                        status=RiskStatusDB(result['status']),
                        rasff_score=result['components']['rasff_score'],
                        lmr_score=result['components']['lmr_score'],
                        phyto_score=result['components']['phyto_score'],
                        logistic_score=result['components']['logistic_score'],
                        penalty=result['components']['penalty'],
                        rasff_alerts_6m=alerts_6m,
                        rasff_alerts_12m=alerts_12m,
                        recommendations=result['recommendations']
                    )
                    
                    db.add(assessment)
            
            db.commit()
            print(f"[SCHEDULER] ✓ Riscos recalculados para {len(products)} produtos")
            
        except Exception as e:
            print(f"[SCHEDULER] ✗ Erro no recálculo: {e}")
        
        finally:
            db.close()
    
    def stop(self):
        """Para scheduler"""
        self.scheduler.shutdown()


# ============================================================================
# 7. INTEGRAÇÃO SISCOMEX (Validação NCM)
# ============================================================================

class SISCOMEXValidator:
    """
    Validador de códigos NCM via SISCOMEX
    Base: https://www.gov.br/siscomex/
    """
    
    BASE_URL = "https://portalunico.siscomex.gov.br/classif"
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
    
    def validate_ncm(self, ncm_code: str) -> Dict:
        """
        Valida código NCM e retorna informações
        
        Returns:
            {
                'valid': bool,
                'description': str,
                'taxes': dict,
                'restrictions': list
            }
        """
        
        # Limpar NCM (apenas números)
        ncm_clean = re.sub(r'\D', '', ncm_code)
        
        if len(ncm_clean) != 8:
            return {'valid': False, 'error': 'NCM deve ter 8 dígitos'}
        
        try:
            # Consultar API (endpoint fictício - ajustar para API real)
            url = f"{self.BASE_URL}/api/ncm/{ncm_clean}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                return {
                    'valid': True,
                    'ncm': ncm_clean,
                    'description': data.get('description', 'N/A'),
                    'taxes': {
                        'ii': data.get('ii', 0),  # Imposto de Importação
                        'ipi': data.get('ipi', 0)  # IPI
                    },
                    'restrictions': data.get('restrictions', [])
                }
            
            else:
                # Fallback: Usar validação básica
                return self._validate_ncm_basic(ncm_clean)
        
        except Exception as e:
            print(f"[SISCOMEX] Erro: {e}")
            return self._validate_ncm_basic(ncm_clean)
    
    def _validate_ncm_basic(self, ncm_code: str) -> Dict:
        """Validação básica de NCM (fallback)"""
        
        # Database simples de NCMs conhecidos
        known_ncms = {
            '09011100': 'Café não torrado, não descafeinado',
            '08119050': 'Açaí',
            '20091100': 'Suco de laranja congelado',
            '12010010': 'Soja para semeadura',
            '08081000': 'Maçãs frescas',
            '04069050': 'Queijo Parmesão',
            '15091090': 'Azeite de oliva virgem'
        }
        
        if ncm_code in known_ncms:
            return {
                'valid': True,
                'ncm': ncm_code,
                'description': known_ncms[ncm_code],
                'taxes': {'ii': 0, 'ipi': 0},
                'restrictions': []
            }
        
        return {
            'valid': False,
            'ncm': ncm_code,
            'error': 'NCM não encontrado na base de dados'
        }


# API endpoint para validação NCM
@app.get("/api/validate-ncm/{ncm_code}")
def validate_ncm_endpoint(ncm_code: str):
    """Valida código NCM"""
    
    validator = SISCOMEXValidator()
    result = validator.validate_ncm(ncm_code)
    
    if not result.get('valid'):
        raise HTTPException(status_code=404, detail=result.get('error', 'Invalid NCM'))
    
    return result


# ============================================================================
# 8. WEBHOOKS (Integração com sistemas externos)
# ============================================================================

class WebhookManager:
    """Gerenciador de webhooks para notificações externas"""
    
    @staticmethod
    def trigger_webhook(url: str, payload: dict) -> bool:
        """Dispara webhook para URL externa"""
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"[WEBHOOK] ✓ Enviado para {url}")
                return True
            else:
                print(f"[WEBHOOK] ✗ Erro {response.status_code} em {url}")
                return False
        
        except Exception as e:
            print(f"[WEBHOOK] ✗ Erro ao enviar: {e}")
            return False
    
    @staticmethod
    def send_risk_alert_webhook(webhook_url: str, product_key: str, score: float, status: str):
        """Envia alerta de risco via webhook"""
        
        payload = {
            'event': 'risk_alert',
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'product_key': product_key,
                'risk_score': score,
                'status': status,
                'severity': 'high' if score > 65 else 'medium'
            }
        }
        
        return WebhookManager.trigger_webhook(webhook_url, payload)


# API endpoint para configurar webhooks
@app.post("/api/webhooks")
def configure_webhook(
    url: str,
    events: List[str],
    db: SessionLocal = Depends(get_db)
):
    """Configura webhook para eventos do sistema"""
    
    # TODO: Salvar configuração de webhook no banco
    
    return {
        'message': 'Webhook configured',
        'url': url,
        'events': events
    }


# ============================================================================
# 9. EXPORT/IMPORT DE DADOS (Backup e Migração)
# ============================================================================

@cli.command()
@click.option('--output', default='backup/zoi_backup.json')
def export_data(output):
    """Exporta todos os dados do sistema"""
    
    db = SessionLocal()
    
    data = {
        'exported_at': datetime.utcnow().isoformat(),
        'version': '2.0',
        'products': [],
        'risk_assessments': [],
        'users': []
    }
    
    # Exportar produtos
    products = db.query(Product).all()
    for p in products:
        data['products'].append({
            'key': p.key,
            'name_pt': p.name_pt,
            'name_it': p.name_it,
            'ncm_code': p.ncm_code,
            'direction': p.direction.value,
            'state': p.state.value
        })
    
    # Exportar avaliações
    assessments = db.query(RiskAssessment).all()
    for a in assessments:
        data['risk_assessments'].append({
            'product_id': a.product_id,
            'score': a.final_score,
            'status': a.status.value,
            'timestamp': a.calculation_timestamp.isoformat()
        })
    
    # Exportar usuários (sem senhas)
    users = db.query(User).all()
    for u in users:
        data['users'].append({
            'email': u.email,
            'full_name': u.full_name,
            'is_admin': u.is_admin
        })
    
    # Salvar
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    click.echo(f"✓ Backup salvo em {output_path}")
    click.echo(f"  Produtos: {len(data['products'])}")
    click.echo(f"  Avaliações: {len(data['risk_assessments'])}")
    click.echo(f"  Usuários: {len(data['users'])}")
    
    db.close()


# ============================================================================
# 10. MAIN APPLICATION RUNNER (CORRIGIDO E ALINHADO)
# ============================================================================

def run_api_server():
    """Inicia servidor FastAPI com ajustes para o Render"""
    import uvicorn
    import os
    
    # Criar tabelas antes de iniciar
    try:
        Base.metadata.create_all(bind=engine)
        print("✓ Banco de dados inicializado.")
    except Exception as e:
        print(f"⚠ Erro no DB: {e}")

    # PORTA DINÂMICA DO RENDER
    port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    import uvicorn
    import os
    
    Base.metadata.create_all(bind=engine)
    
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
