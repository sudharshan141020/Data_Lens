from app.analyzers.base_analyzer import BaseAnalyzer


class RealEstateAnalyzer(BaseAnalyzer):
    domain_name = "real_estate"

    # Property type and location are the two headline breakdowns for a
    # real estate dataset -- "what kind of property" and "where" are the
    # two things a listing's price is almost always sliced by.
    headline_dimension_roles = {"PROPERTY_TYPE", "LOCATION"}

    key_kpis = [
        "Average Sale Price", "Average Listing Price", "Days on Market",
        "Square Footage", "Bedrooms", "Property Types", "Neighborhoods",
    ]
