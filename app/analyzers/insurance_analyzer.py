from app.analyzers.base_analyzer import BaseAnalyzer


class InsuranceAnalyzer(BaseAnalyzer):
    domain_name = "insurance"

    # Coverage type and claim status are the two headline breakdowns for
    # insurance data -- premium/claims almost always get sliced by what
    # kind of policy it is, and claim status is the metric everything
    # else (loss ratio, processing time) ultimately gets read against.
    headline_dimension_roles = {"COVERAGE_TYPE", "CLAIM_STATUS"}

    key_kpis = [
        "Total Premium", "Total Claims", "Average Claim Amount",
        "Claim Status", "Coverage Types", "Average Risk Score",
    ]
