"""
Runtime Two Handler - Dual-capability serverless runtime

This module implements the main server for Runtime Two that supports both:
1. Traditional remote execution (via RemoteExecutor)
2. HTTP endpoint exposure (via FastAPI)
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from class_registry import ClassRegistry
from remote_executor import RemoteExecutor
from remote_execution import FunctionRequest, FunctionResponse
from serialization_utils import SerializationUtils

log = logging.getLogger(__name__)


class RuntimeTwoServer:
    """
    Runtime Two server that provides dual execution capabilities:
    - Remote execution for programmatic calls
    - HTTP endpoints for decorated methods
    """
    
    def __init__(self):
        self.remote_executor = RemoteExecutor()
        self.class_registry = ClassRegistry()
        self.app = FastAPI(title="Runtime Two Server", version="1.0.0")
        self.port = int(os.environ.get("PORT", 8000))
        
        # Setup routes
        self._setup_routes()
        
        log.info("Runtime Two server initialized")
    
    def _setup_routes(self):
        """Setup FastAPI routes for HTTP endpoints."""
        
        # Health check endpoint
        @self.app.get("/health")
        async def health_check():
            return {
                "status": "healthy", 
                "runtime": "two",
                "capabilities": ["remote_execution", "http_endpoints"]
            }
        
        # RunPod ping endpoint for health checks
        @self.app.get("/ping")
        async def ping():
            return {"ping": "pong"}
        
        # Traditional remote execution endpoint (for @remote calls)
        @self.app.post("/execute")
        async def remote_execution(request: Request):
            """Handle traditional remote execution requests via ClassRegistry."""
            try:
                # Get request data
                event = await request.json()
                input_data = FunctionRequest(**event.get("input", {}))
                
                # Route through ClassRegistry for unified class management
                if input_data.execution_type == "class":
                    log.debug(f"Remote class execution: {input_data.class_name}.{input_data.method_name}")
                    
                    # Check if class needs registration and HTTP endpoint creation
                    if input_data.class_name not in self.class_registry.deployed_classes:
                        class_info = await self.class_registry.register_class(input_data)
                        # Create HTTP endpoints for @endpoint decorated methods
                        await self._create_http_routes(class_info)
                    
                    # Execute method via ClassRegistry
                    result = await self.class_registry.execute_class_method(input_data)
                    
                    # Return successful response
                    response = FunctionResponse(
                        success=True,
                        result=SerializationUtils.serialize_result(result),
                        instance_id=input_data.instance_id
                    )
                    
                else:
                    # Function execution (non-class) - use RemoteExecutor
                    log.debug(f"Remote function execution: {input_data.function_name}")
                    response = await self.remote_executor.ExecuteFunction(input_data)
                
                return response.model_dump()
                
            except Exception as e:
                log.error(f"Remote execution error: {e}")
                error_response = FunctionResponse(
                    success=False,
                    error=f"Runtime Two remote execution error: {str(e)}"
                )
                return error_response.model_dump()
        
        # Dynamic HTTP endpoint routes will be added here
        # when classes are registered
    
    async def register_class_endpoints(self, class_request: FunctionRequest):
        """
        Register a class and create HTTP endpoints for @endpoint decorated methods.
        
        Args:
            class_request: FunctionRequest containing class information
        """
        try:
            # Register the class in our registry
            class_info = await self.class_registry.register_class(class_request)
            
            # Create HTTP routes for @endpoint methods
            await self._create_http_routes(class_info)
            
            log.info(f"Registered class {class_request.class_name} with {len(class_info['endpoints'])} HTTP endpoints")
            
        except Exception as e:
            log.error(f"Failed to register class {class_request.class_name}: {e}")
            raise
    
    async def _create_http_routes(self, class_info: Dict[str, Any]):
        """Create HTTP routes for class endpoint methods."""
        
        class_name = class_info['class_name']
        endpoints = class_info['endpoints']
        
        for endpoint_info in endpoints:
            method_name = endpoint_info['method_name']
            http_methods = endpoint_info['http_methods']
            route = endpoint_info['route']
            
            # Create route handler
            handler = self._create_route_handler(class_name, method_name)
            
            # Add route for each HTTP method
            for http_method in http_methods:
                self.app.add_api_route(
                    path=route,
                    endpoint=handler,
                    methods=[http_method],
                    name=f"{class_name}_{method_name}_{http_method.lower()}"
                )
            
            log.debug(f"Created HTTP route {http_methods} {route} -> {class_name}.{method_name}")
    
    def _create_route_handler(self, class_name: str, method_name: str):
        """Create a FastAPI route handler for a class method."""
        
        async def route_handler(request: Request):
            try:
                # Get request data
                if request.method == "GET":
                    data = dict(request.query_params)
                else:
                    data = await request.json()
                
                log.debug(f"HTTP call to {class_name}.{method_name} with data: {data}")
                
                # Execute method via class registry
                result = await self.class_registry.execute_method(
                    class_name, method_name, data
                )
                
                return JSONResponse(content=result)
                
            except Exception as e:
                log.error(f"HTTP endpoint error for {class_name}.{method_name}: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Method execution failed: {str(e)}"
                )
        
        return route_handler
    
    async def start_server(self):
        """Start the Runtime Two server."""
        log.info(f"Starting Runtime Two server on port {self.port}")
        
        # Run FastAPI with uvicorn
        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0", 
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()


# Singleton server instance
_server_instance: Optional[RuntimeTwoServer] = None

def get_server() -> RuntimeTwoServer:
    """Get or create the Runtime Two server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = RuntimeTwoServer()
    return _server_instance


# Runtime Two runs as pure FastAPI server - no traditional handler function needed


# For standalone HTTP server mode
if __name__ == "__main__":
    # Check if we should run in HTTP server mode
    if os.environ.get("RUNTIME_MODE") == "http" or os.environ.get("ENABLE_HTTP_SERVER") == "true":
        server = get_server()
        asyncio.run(server.start_server())
    else:
        log.info("Runtime Two handler ready for serverless execution")