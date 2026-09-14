from app.analyzers.base_analyzer import BaseAnalyzer


class EcommerceAnalyzer(BaseAnalyzer):
    domain_name = "ecommerce"

    # Cart status (abandoned vs. completed) and payment method are the
    # two headline breakdowns for e-commerce session/cart data --
    # distinct from the existing sales/retail domains, which assume
    # completed transactions rather than in-progress carts.
    headline_dimension_roles = {"CART_STATUS", "PAYMENT_METHOD"}

    key_kpis = [
        "Average Cart Value", "Cart Abandonment Rate", "Conversion Rate",
        "Page Views", "Payment Methods",
    ]
