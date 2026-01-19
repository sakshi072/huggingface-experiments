from typing import TypedDict, List, Dict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class SupervisorState(TypedDict):
    """State for job search workflow."""
    # Input
    user_query:str
    max_results:int
    time_window_hours:int

    # Job Search output
    final_results:  Optional[List[dict]]

    # Messages
    messages: Annotated[List[BaseMessage], add_messages]

    # Errors
    errors: List[str]