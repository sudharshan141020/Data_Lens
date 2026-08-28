"""
Maps a detected domain name to its analyzer plugin. This is the ONLY place
that needs to change when a new domain analyzer is added — nowhere else in
the codebase branches on domain name.
"""
from app.analyzers.base_analyzer import BaseAnalyzer
from app.analyzers.healthcare_analyzer import HealthcareAnalyzer
from app.analyzers.sales_analyzer import SalesAnalyzer
from app.analyzers.retail_analyzer import RetailAnalyzer
from app.analyzers.manufacturing_analyzer import ManufacturingAnalyzer
from app.analyzers.education_analyzer import EducationAnalyzer
from app.analyzers.hr_analyzer import HRAnalyzer
from app.analyzers.traffic_analyzer import TrafficAnalyzer
from app.analyzers.finance_analyzer import FinanceAnalyzer
from app.analyzers.generic_analyzer import GenericAnalyzer

REGISTRY = {
    "healthcare": HealthcareAnalyzer,
    "sales": SalesAnalyzer,
    "retail": RetailAnalyzer,
    "manufacturing": ManufacturingAnalyzer,
    "education": EducationAnalyzer,
    "hr": HRAnalyzer,
    "traffic": TrafficAnalyzer,
    "finance": FinanceAnalyzer,
    "generic": GenericAnalyzer,
}


def get_analyzer(domain: str, df, profile) -> BaseAnalyzer:
    analyzer_cls = REGISTRY.get(domain, GenericAnalyzer)
    return analyzer_cls(df, profile)
