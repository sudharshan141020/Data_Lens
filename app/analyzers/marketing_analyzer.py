from app.analyzers.base_analyzer import BaseAnalyzer


class MarketingAnalyzer(BaseAnalyzer):
    domain_name = "marketing"

    # Campaign and channel breakdowns are the headline views for a
    # marketing dataset -- distinct from sales (product/region) and
    # retail (store/category). This domain is about campaign performance
    # and ad efficiency, not transactions.
    headline_dimension_roles = {"CAMPAIGN", "CHANNEL"}

    key_kpis = [
        "Ad Spend", "Impressions", "Clicks", "CTR", "Conversion Rate",
        "ROAS", "Campaigns", "Channels",
    ]
