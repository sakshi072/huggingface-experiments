from fastapi import HTTPException, Request
import logging
from fastapi.responses import JSONResponse
import uuid

logger = logging.getLogger(__name__)

async def general_exception_handler(request: Request, exc: Exception):
    """
    Global exception to catch all unhandled exceptions
    """
    request_id = request.state.request_id 
    logger.error(f"[{request_id}] Unhandled Exception: {str(exc)}", exc_info=True)   

    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unhandled internal server error occurred",
            "error_type": exc.__class__.__name__,
            "request_id": request_id
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException):                                                                                                                                 
      request_id = request.state.request_id                                                                                                                                                         
      logger.warning(f"[{request_id}] {request.method} {request.url.path} → {exc.status_code}: {exc.detail}")                                                                                             
                                                                                                                                                                                                          
      return JSONResponse(                                                                                                                                                                                
          status_code=exc.status_code,                                                                                                                                                                    
          content={                                                                                                                                                                                       
              "error": exc.detail,                                                                                                                                                                        
              "request_id": request_id                                                                                                                                                                    
          }                                                                                                                                                                                               
      )    
