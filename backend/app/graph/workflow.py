from langgraph.graph import StateGraph, END
from app.graph.state import AgentState
from app.services.market_data_service import MarketDataService

# These would ideally be proper LangChain agent nodes utilizing LLMs.
# For the initial setup, we define the structure of the nodes.

def orchestrator_node(state: AgentState):
    """Determines what information is needed based on query."""
    # Mocking orchestrator extracting 'tomato'
    return {"context": {"commodity": "tomato", "quantity_kg": 2000, "location": "Coimbatore"}}

def farmer_context_node(state: AgentState):
    """Fetches farmer constraints from DB if farmer_id exists."""
    return {"context": {"storage_available": True}}

def market_agent_node(state: AgentState):
    """Fetches current market prices and arrivals."""
    commodity = state["context"].get("commodity", "")
    location = state["context"].get("location", "")
    prices = MarketDataService.get_current_prices(commodity, location)
    return {"market_data": prices}

def trend_agent_node(state: AgentState):
    """Calculates trends and opportunity."""
    return {"trend_analysis": {"price_change_7d_pct": 8.4, "opportunity_score": 74.0}}

def logistics_node(state: AgentState):
    """Calculates transport and net realization."""
    return {"logistics_data": {"estimated_transport_cost": 1000, "estimated_net_realization": 55000}}

def rag_agent_node(state: AgentState):
    """Retrieves supporting RAG documents."""
    return {"rag_evidence": [{"doc": "Agri Guidelines 2026", "relevance": 0.9}]}

def decision_agent_node(state: AgentState):
    """Synthesizes all gathered data into a final recommendation."""
    rec = {
        "type": "SELL_AT_MARKET_A",
        "confidence": 0.78,
        "risk_level": "MEDIUM",
        "reasoning": ["Highest modal price observed."]
    }
    return {"recommendation": rec}

def create_workflow():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("farmer_context", farmer_context_node)
    workflow.add_node("market_agent", market_agent_node)
    workflow.add_node("trend_agent", trend_agent_node)
    workflow.add_node("logistics_agent", logistics_node)
    workflow.add_node("rag_agent", rag_agent_node)
    workflow.add_node("decision_agent", decision_agent_node)
    
    workflow.set_entry_point("orchestrator")
    
    workflow.add_edge("orchestrator", "farmer_context")
    workflow.add_edge("farmer_context", "market_agent")
    workflow.add_edge("market_agent", "logistics_agent")
    workflow.add_edge("logistics_agent", "trend_agent")
    workflow.add_edge("trend_agent", "rag_agent")
    workflow.add_edge("rag_agent", "decision_agent")
    workflow.add_edge("decision_agent", END)
    
    return workflow.compile()

# compiled graph instance
agrimitra_graph = create_workflow()
