from app.analyzers.base_analyzer import BaseAnalyzer


class SaasAnalyzer(BaseAnalyzer):
    domain_name = "saas"

    # Plan tier and churn status are the two headline breakdowns for a
    # subscription dataset -- MRR/ARR almost always gets sliced by which
    # plan a customer is on, and churn is the metric everything else in
    # a SaaS business ultimately gets read against.
    headline_dimension_roles = {"SUBSCRIPTION_PLAN", "CHURN_STATUS"}

    key_kpis = [
        "MRR", "ARR", "Churn Rate", "Active Subscriptions",
        "Plans", "Seats", "NPS",
    ]
