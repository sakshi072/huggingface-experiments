from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langchain.messages import HumanMessage
from .job_search_workflow import create_job_search_graph
from models import SupervisorState
import logging
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

# Compile subgraph once
job_search_graph = create_job_search_graph()

def formatter_results_node(state:SupervisorState):
    results = state.get("final_results", [])

    if not results:
        return {"messages": [AIMessage(content="I couldn't find any specific AI Software Engineer openings in California at the moment. Would you like to try a different location?")]}
    
    logger.info(f"Formatter received {len(results)} results from state keys: {state.keys()}")
    
    # Build a clean Markdown list
    response_text = "### 🚀 Latest AI Software Engineer Jobs in California\n\n"
    for job in results:
        # job is likely a dict or JobListing object
        title = job.get('title') if isinstance(job, dict) else job.title
        company = job.get('company') if isinstance(job, dict) else job.company
        url = job.get('url') if isinstance(job, dict) else job.url
        location = job.get('location') if isinstance(job, dict) else job.location

        response_text += f"- **{title}** at {company}\n"
        response_text += f"  📍 {location}\n"
        response_text += f"  🔗 [View Posting]({url})\n\n"

    return {"messages": [AIMessage(content=response_text)]}

def should_continue(state:SupervisorState):
    # If we have results, always format them
    if state.get("final_results"):
        return "formatter"
    # Only retry if there's an error AND we haven't tried too many times 
    # (Requires adding a 'retry_count' to your state)
    if state.get("errors"):
        return END # Or a specific error_handler node
    return "formatter"

def create_supervisor_graph(checkpointer=None):
    supervisor_workflow = StateGraph(SupervisorState)

    supervisor_workflow.add_node("job_search", job_search_graph)
    supervisor_workflow.add_node("formatter", formatter_results_node)

    supervisor_workflow.set_entry_point("job_search")
    supervisor_workflow.add_conditional_edges(
        "job_search", 
        should_continue,
        {
            "job_search": "job_search",
            "formatter":"formatter",
            END:END
        })
    supervisor_workflow.add_edge("formatter", END)

    return supervisor_workflow.compile(checkpointer=checkpointer)