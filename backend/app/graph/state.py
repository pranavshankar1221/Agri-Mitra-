from typing import TypedDict, Annotated, List, Dict, Any
import operator

def merge_dicts(a: dict, b: dict) -> dict:
    # A simple merger for dicts
    return {**a, **b}

class AgentState(TypedDict):
    query: str
    farmer_id: str | None
    
    # State accumulated across workflow
    context: Annotated[dict, merge_dicts]
    market_data: Annotated[list, operator.add]
    trend_analysis: Annotated[dict, merge_dicts]
    logistics_data: Annotated[dict, merge_dicts]
    rag_evidence: Annotated[list, operator.add]
    
    # Final recommendation
    recommendation: dict | None
    
    # Error tracking
    errors: Annotated[list, operator.add]
