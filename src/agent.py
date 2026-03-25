from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from .tools import fetch_latest_nav_batch, calculate_portfolio_value


class State(TypedDict):
    """Main state for FinAgent.
    
    Tracks portfolio data, user goals, and the next action to take.
    """
    portfolio_data: Dict[str, Any]
    user_goals: List[Dict[str, Any]]
    next_action: str


def create_initial_state() -> State:
    """Create a fresh state for a new session."""
    return {
        "portfolio_data": {},
        "user_goals": [],
        "next_action": "initialize"
    }


def build_agent_graph() -> StateGraph:
    """Build and compile the FinAgent LangGraph."""
    workflow = StateGraph(State)
    
    def initialize_node(state: State) -> State:
        """Initialize the session."""
        state["next_action"] = "check_goals"
        return state
    
    def check_goals_node(state: State) -> State:
        """Check if any user goals require portfolio valuation."""
        for goal in state.get("user_goals", []):
            if goal.get("type") == "valuation" or goal.get("requires_valuation"):
                state["next_action"] = "valuation"
                return state
        state["next_action"] = "ready"
        return state
    
    def valuation_node(state: State) -> State:
        """Fetch NAV data and calculate portfolio value if holdings exist."""
        portfolio = state.get("portfolio_data", {})
        holdings = portfolio.get("holdings", [])
        
        if holdings:
            # Convert portfolio holdings to format expected by tools
            tool_holdings = []
            for h in holdings:
                tool_holdings.append({
                    "scheme_code": h.get("symbol"),
                    "units": h.get("quantity", 0)
                })
            
            nav_data = fetch_latest_nav_batch()
            valuation = calculate_portfolio_value(tool_holdings, nav_data)
            
            # Update portfolio_data with valuation results
            state["portfolio_data"]["last_valuation"] = valuation
            
        state["next_action"] = "ready"
        return state
    
    workflow.add_node("initialize", initialize_node)
    workflow.add_node("check_goals", check_goals_node)
    workflow.add_node("valuation", valuation_node)
    workflow.add_node("ready", lambda x: x)
    
    workflow.set_entry_point("initialize")
    workflow.add_edge("initialize", "check_goals")
    workflow.add_conditional_edges(
        "check_goals",
        lambda state: state["next_action"],
        {
            "valuation": "valuation",
            "ready": "ready"
        }
    )
    workflow.add_edge("valuation", "ready")
    workflow.add_edge("ready", END)
    
    return workflow.compile(checkpointer=MemorySaver())


# Global compiled graph instance
finagent_graph = build_agent_graph()
