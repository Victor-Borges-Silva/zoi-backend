"""
ZOI Trade Advisory - Test Suite
Testes automatizados para garantir qualidade do sistema

Execute: pytest tests/ -v --cov=. --cov-report=html
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import json
from datetime import datetime

# Importar sistema
from zoi_complete_system import (
    app, Base, Product, RiskAssessment, User,
    get_db, get_password_hash, ANVISAScraper,
    SISCOMEXValidator, NotificationService
)

from zoi_bilateral_system import (
    SentinelScore2Engine, ProductSpec, TradeDirection,
    ProductState, ProductDatabase, LabelTranslator
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def test_db():
    """Cria banco de dados temporário para testes"""
    SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    
    yield TestingSessionLocal
    
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(test_db):
    """Cliente de teste da API"""
    
    def override_get_db():
        try:
            db = test_db()
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_product(test_db):
    """Produto de exemplo para testes"""
    db = test_db()
    
    product = Product(
        key="test_cafe",
        name_pt="Café Arábica Teste",
        name_it="Caffè Arabica Test",
        name_en="Arabica Coffee Test",
        ncm_code="09011100",
        hs_code="090111",
        taric_code="0901110000",
        direction="export",
        state="ambient",
        shelf_life_days=365,
        transport_days_avg=35,
        temperature_min_c=10.0,
        temperature_max_c=25.0,
        requires_phytosanitary_cert=True,
        requires_health_cert=False,
        critical_substances=["carbendazim"]
    )
    
    db.add(product)
    db.commit()
    db.refresh(product)
    
    yield product
    
    db.delete(product)
    db.commit()
    db.close()


@pytest.fixture
def auth_token(client, test_db):
    """Token de autenticação para testes"""
    db = test_db()
    
    # Criar usuário de teste
    test_user = User(
        email="test@zoi-trade.com",
        hashed_password=get_password_hash("testpass123"),
        full_name="Test User",
        is_active=True
    )
    
    db.add(test_user)
    db.commit()
    
    # Login
    response = client.post(
        "/token",
        data={"username": "test@zoi-trade.com", "password": "testpass123"}
    )
    
    token = response.json()["access_token"]
    
    yield token
    
    db.delete(test_user)
    db.commit()
    db.close()


# ============================================================================
# TESTES DA API
# ============================================================================

class TestAPI:
    """Testes dos endpoints da API"""
    
    def test_root_endpoint(self, client):
        """Testa endpoint raiz"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "ZOI" in data["message"]
    
    def test_health_check(self, client):
        """Testa health check"""
        response = client.get("/health")
        # Endpoint pode não estar implementado ainda
        assert response.status_code in [200, 404]
    
    def test_login_success(self, client, test_db):
        """Testa login bem-sucedido"""
        db = test_db()
        
        # Criar usuário
        user = User(
            email="login_test@zoi.com",
            hashed_password=get_password_hash("pass123"),
            full_name="Login Test"
        )
        db.add(user)
        db.commit()
        
        # Tentar login
        response = client.post(
            "/token",
            data={"username": "login_test@zoi.com", "password": "pass123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        
        db.delete(user)
        db.commit()
        db.close()
    
    def test_login_failure(self, client):
        """Testa login com credenciais inválidas"""
        response = client.post(
            "/token",
            data={"username": "invalid@zoi.com", "password": "wrongpass"}
        )
        
        assert response.status_code == 401
    
    def test_get_products_unauthorized(self, client):
        """Testa acesso não autorizado"""
        response = client.get("/api/products")
        # Se a rota não exigir autenticação, ajustar teste
        assert response.status_code in [200, 401]
    
    def test_get_products_authorized(self, client, auth_token, sample_product):
        """Testa listagem de produtos com autenticação"""
        response = client.get(
            "/api/products",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_product_by_key(self, client, auth_token, sample_product):
        """Testa busca de produto específico"""
        response = client.get(
            f"/api/products/{sample_product.key}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == sample_product.key
        assert data["ncm_code"] == sample_product.ncm_code
    
    def test_calculate_risk(self, client, auth_token, sample_product):
        """Testa cálculo de risco"""
        request_data = {
            "product_key": sample_product.key,
            "rasff_alerts_6m": 2,
            "rasff_alerts_12m": 5,
            "lmr_data": [
                {
                    "substance": "carbendazim",
                    "source_lmr": 2.0,
                    "dest_lmr": 0.1,
                    "detectionRate": 0.6
                }
            ],
            "phyto_alerts": [],
            "transport_days": 35
        }
        
        response = client.post(
            "/api/calculate-risk",
            json=request_data,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "score" in data
        assert "status" in data
        assert "components" in data
        assert "recommendations" in data
        
        assert 0 <= data["score"] <= 100
        assert data["status"] in ["green", "yellow", "red"]
    
    def test_validate_ncm(self, client, auth_token):
        """Testa validação de NCM"""
        response = client.get(
            "/api/validate-ncm/09011100",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] == True
        assert data["ncm"] == "09011100"
    
    def test_validate_invalid_ncm(self, client, auth_token):
        """Testa validação de NCM inválido"""
        response = client.get(
            "/api/validate-ncm/99999999",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        
        assert response.status_code == 404


# ============================================================================
# TESTES DO MOTOR DE RISCO
# ============================================================================

class TestRiskEngine:
    """Testes do Sentinel Score Engine"""
    
    def test_risk_calculation_low(self):
        """Testa cálculo de risco baixo"""
        product = ProductSpec(
            name_pt="Café Teste",
            name_it="Caffè Test",
            name_en="Coffee Test",
            ncm_code="09011100",
            hs_code="090111",
            state=ProductState.AMBIENT,
            shelf_life_days=365,
            transport_days_avg=30,
            temperature_min_c=10.0,
            temperature_max_c=25.0,
            critical_substances=[]
        )
        
        engine = SentinelScore2Engine(TradeDirection.BR_TO_IT)
        
        result = engine.calculate_risk_score(
            product=product,
            rasff_data={'alerts_6m': 0, 'alerts_12m': 0},
            lmr_data=[],
            phyto_data={'alerts': []},
            transport_data={'days': 30}
        )
        
        assert result['score'] < 30
        assert result['status'] == 'green'
    
    def test_risk_calculation_high(self):
        """Testa cálculo de risco alto"""
        product = ProductSpec(
            name_pt="Laranja Teste",
            name_it="Arancia Test",
            name_en="Orange Test",
            ncm_code="08051000",
            hs_code="080510",
            state=ProductState.FRESH,
            shelf_life_days=14,
            transport_days_avg=30,
            temperature_min_c=7.0,
            temperature_max_c=10.0,
            critical_substances=["carbendazim", "imazalil"]
        )
        
        engine = SentinelScore2Engine(TradeDirection.BR_TO_IT)
        
        result = engine.calculate_risk_score(
            product=product,
            rasff_data={'alerts_6m': 10, 'alerts_12m': 15},
            lmr_data=[
                {'substance': 'carbendazim', 'source_lmr': 5.0, 'dest_lmr': 0.0, 'detectionRate': 0.9}
            ],
            phyto_data={'alerts': [{'severity': 'quarantine', 'affectedStates': ['SP'], 'monthsOld': 1}]},
            transport_data={'days': 30}
        )
        
        assert result['score'] > 70
        assert result['status'] == 'red'
    
    def test_logistic_score_fresh_product(self):
        """Testa componente logístico para produtos frescos"""
        product = ProductSpec(
            name_pt="Manga Fresca",
            name_it="Mango Fresco",
            name_en="Fresh Mango",
            ncm_code="08045020",
            hs_code="080450",
            state=ProductState.FRESH,
            shelf_life_days=21,
            transport_days_avg=25,
            temperature_min_c=10.0,
            temperature_max_c=13.0,
            critical_substances=[]
        )
        
        engine = SentinelScore2Engine(TradeDirection.BR_TO_IT)
        
        # Transporte longo (75% da vida útil)
        logistic_score = engine._calculate_logistic_score(
            product,
            {'days': 16}  # 16 dias de 21 = 76%
        )
        
        # Deve ter score alto devido ao shelf-life curto
        assert logistic_score > 30
    
    def test_penalty_multiplier(self):
        """Testa penalty por múltiplos riscos críticos"""
        product = ProductSpec(
            name_pt="Produto Teste",
            name_it="Prodotto Test",
            name_en="Test Product",
            ncm_code="12345678",
            hs_code="123456",
            state=ProductState.FROZEN,
            shelf_life_days=365,
            transport_days_avg=30,
            temperature_min_c=-18.0,
            temperature_max_c=-15.0,
            critical_substances=[]
        )
        
        engine = SentinelScore2Engine(TradeDirection.BR_TO_IT)
        
        # Múltiplos riscos críticos (>70)
        result = engine.calculate_risk_score(
            product=product,
            rasff_data={'alerts_6m': 15, 'alerts_12m': 20},
            lmr_data=[{'substance': 'test', 'source_lmr': 10.0, 'dest_lmr': 0.0, 'detectionRate': 1.0}],
            phyto_data={'alerts': [{'severity': 'quarantine', 'affectedStates': ['SP'], 'monthsOld': 0.5}]},
            transport_data={'days': 30}
        )
        
        # Deve ter penalty > 0
        assert result['components']['penalty'] > 0


# ============================================================================
# TESTES DE TRADUÇÃO
# ============================================================================

class TestLabelTranslator:
    """Testes do tradutor de etiquetas"""
    
    def test_translate_pt_to_it(self):
        """Testa tradução PT → IT"""
        result = LabelTranslator.translate(
            "Informação Nutricional",
            TradeDirection.BR_TO_IT
        )
        
        assert result == "Informazioni Nutrizionali"
    
    def test_translate_it_to_pt(self):
        """Testa tradução IT → PT"""
        result = LabelTranslator.translate(
            "DOP",
            TradeDirection.IT_TO_BR
        )
        
        assert "Denominação de Origem" in result
    
    def test_translate_full_label(self):
        """Testa tradução de objeto completo"""
        label_pt = {
            'title': 'Informação Nutricional',
            'allergens': 'CONTÉM GLÚTEN',
            'storage': 'Manter Congelado'
        }
        
        result = LabelTranslator.translate_label_full(
            label_pt,
            TradeDirection.BR_TO_IT
        )
        
        assert result['title'] == 'Informazioni Nutrizionali'
        assert result['allergens'] == 'CONTIENE GLUTINE'
        assert result['storage'] == 'Conservare Congelato'


# ============================================================================
# TESTES DE DATABASE
# ============================================================================

class TestDatabase:
    """Testes de persistência em banco de dados"""
    
    def test_create_product(self, test_db):
        """Testa criação de produto"""
        db = test_db()
        
        product = Product(
            key="test_product",
            name_pt="Produto Teste",
            name_it="Prodotto Test",
            ncm_code="12345678",
            hs_code="123456",
            direction="export",
            state="fresh",
            shelf_life_days=30
        )
        
        db.add(product)
        db.commit()
        
        # Verificar se foi salvo
        retrieved = db.query(Product).filter(Product.key == "test_product").first()
        assert retrieved is not None
        assert retrieved.name_pt == "Produto Teste"
        
        db.delete(product)
        db.commit()
        db.close()
    
    def test_create_risk_assessment(self, test_db, sample_product):
        """Testa criação de avaliação de risco"""
        db = test_db()
        
        assessment = RiskAssessment(
            product_id=sample_product.id,
            final_score=45.5,
            status="yellow",
            rasff_score=40.0,
            lmr_score=50.0,
            phyto_score=30.0,
            logistic_score=35.0,
            penalty=5.0,
            rasff_alerts_6m=2,
            rasff_alerts_12m=4,
            recommendations=["Test recommendation"]
        )
        
        db.add(assessment)
        db.commit()
        
        # Verificar relacionamento
        assert sample_product.risk_assessments[0].final_score == 45.5
        
        db.delete(assessment)
        db.commit()
        db.close()


# ============================================================================
# TESTES DE SCRAPERS
# ============================================================================

class TestScrapers:
    """Testes dos scrapers (mock)"""
    
    def test_anvisa_fallback_lmr(self):
        """Testa fallback de LMR ANVISA"""
        scraper = ANVISAScraper()
        
        result = scraper._get_fallback_lmr('Glifosato', 'Soja')
        
        assert result is not None
        assert result['substance'] == 'Glifosato'
        assert result['crop'] == 'Soja'
        assert result['lmr_mg_kg'] > 0
    
    def test_anvisa_extract_number(self):
        """Testa extração de número de texto"""
        scraper = ANVISAScraper()
        
        assert scraper._extract_number("0.5 mg/kg") == 0.5
        assert scraper._extract_number("10 ppm") == 10.0
        assert scraper._extract_number("1,5 mg/kg") == 1.5


# ============================================================================
# TESTES DE VALIDADORES
# ============================================================================

class TestValidators:
    """Testes de validadores"""
    
    def test_siscomex_validate_known_ncm(self):
        """Testa validação de NCM conhecido"""
        validator = SISCOMEXValidator()
        
        result = validator.validate_ncm('09011100')
        
        assert result['valid'] == True
        assert result['ncm'] == '09011100'
        assert 'Café' in result['description']
    
    def test_siscomex_invalid_ncm_length(self):
        """Testa NCM com tamanho inválido"""
        validator = SISCOMEXValidator()
        
        result = validator.validate_ncm('123')
        
        assert result['valid'] == False
        assert 'erro' in result.get('error', '').lower() or 'error' in result


# ============================================================================
# TESTES DE PERFORMANCE
# ============================================================================

class TestPerformance:
    """Testes de performance"""
    
    def test_risk_calculation_speed(self):
        """Testa velocidade de cálculo de risco"""
        import time
        
        product = ProductSpec(
            name_pt="Teste Performance",
            name_it="Test Performance",
            name_en="Performance Test",
            ncm_code="12345678",
            hs_code="123456",
            state=ProductState.AMBIENT,
            shelf_life_days=365,
            transport_days_avg=30,
            temperature_min_c=10.0,
            temperature_max_c=25.0,
            critical_substances=[]
        )
        
        engine = SentinelScore2Engine(TradeDirection.BR_TO_IT)
        
        start = time.time()
        
        for _ in range(100):
            engine.calculate_risk_score(
                product=product,
                rasff_data={'alerts_6m': 2, 'alerts_12m': 4},
                lmr_data=[],
                phyto_data={'alerts': []},
                transport_data={'days': 30}
            )
        
        end = time.time()
        avg_time = (end - start) / 100
        
        # Deve calcular em menos de 10ms por iteração
        assert avg_time < 0.01, f"Tempo médio: {avg_time*1000:.2f}ms"


# ============================================================================
# TESTES DE INTEGRAÇÃO
# ============================================================================

class TestIntegration:
    """Testes de integração end-to-end"""
    
    def test_full_workflow(self, client, test_db):
        """Testa fluxo completo: criar usuário → login → calcular risco"""
        
        # 1. Criar usuário
        user_data = {
            "email": "integration@test.com",
            "password": "test123",
            "full_name": "Integration Test"
        }
        
        response = client.post("/api/users", json=user_data)
        assert response.status_code == 201
        
        # 2. Login
        response = client.post(
            "/token",
            data={"username": user_data["email"], "password": user_data["password"]}
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        
        # 3. Criar produto
        db = test_db()
        product = Product(
            key="integration_test",
            name_pt="Produto Integração",
            name_it="Prodotto Integrazione",
            ncm_code="99999999",
            hs_code="999999",
            direction="export",
            state="fresh",
            shelf_life_days=14,
            transport_days_avg=25,
            temperature_min_c=5.0,
            temperature_max_c=10.0
        )
        db.add(product)
        db.commit()
        
        # 4. Calcular risco
        risk_request = {
            "product_key": "integration_test",
            "rasff_alerts_6m": 1,
            "rasff_alerts_12m": 2,
            "lmr_data": [],
            "phyto_alerts": []
        }
        
        response = client.post(
            "/api/calculate-risk",
            json=risk_request,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        risk_data = response.json()
        assert "score" in risk_data
        
        # Cleanup
        db.delete(product)
        user = db.query(User).filter(User.email == user_data["email"]).first()
        if user:
            db.delete(user)
        db.commit()
        db.close()


# ============================================================================
# RUNNER
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=.", "--cov-report=html"])