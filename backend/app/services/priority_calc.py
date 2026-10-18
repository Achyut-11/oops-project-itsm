def priority_calc(affected_percentage:float, buisness_criticality:str, estimated_complexity: str) -> str:
    crit_scores = {
        "LOW" :0,
        "MEDIUM": 50,
        "HIGH":100
    }

    comp_scores = {
        "LOW" :0,
        "MEDIUM": 50,
        "HIGH":100
    }

    score = affected_percentage*0.5+crit_scores[buisness_criticality]*0.35+comp_scores[estimated_complexity]*0.15

    if score >= 80:
        return "P1"
    elif score >= 60:
        return "P2"
    elif score >= 35:
        return "P3"
    else:
        return "P4"