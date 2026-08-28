from app.analyzers.base_analyzer import BaseAnalyzer


class ManufacturingAnalyzer(BaseAnalyzer):
    domain_name = "manufacturing"

    # Production line and machine-level breakdowns are the headline views
    # for a manufacturing dataset -- distinct from retail (store/category)
    # and sales (region/category). This domain is about production
    # throughput and quality, not transactions.
    headline_dimension_roles = {"PRODUCTION_LINE", "MACHINE"}

    key_kpis = [
        "Units Produced", "Defect Rate", "Downtime", "Machine Utilization",
        "Production Line Performance", "Shift Output", "Throughput",
    ]
