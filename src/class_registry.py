"""
Class Registry for Runtime Two

This module manages deployed classes and their HTTP endpoint mappings.
It handles class instantiation, method execution, and endpoint discovery.
"""

import inspect
import logging
import uuid
from typing import Dict, Any, List, Optional, Type
from datetime import datetime

from remote_execution import FunctionRequest
from serialization_utils import SerializationUtils

log = logging.getLogger(__name__)


class ClassRegistry:
    """
    Manages deployed classes and their HTTP endpoint mappings.
    
    Provides:
    - Class registration and instantiation
    - HTTP endpoint discovery from @endpoint decorators
    - Method execution routing
    - Instance lifecycle management
    """
    
    def __init__(self):
        self.deployed_classes: Dict[str, Dict[str, Any]] = {}
        self.class_instances: Dict[str, Any] = {}
        self.instance_metadata: Dict[str, Dict] = {}
        
        log.info("Class registry initialized")
    
    async def register_class(self, class_request: FunctionRequest) -> Dict[str, Any]:
        """
        Register a class for both remote and HTTP execution.
        
        Args:
            class_request: FunctionRequest containing class information
            
        Returns:
            Dictionary containing class info and discovered endpoints
        """
        class_name = class_request.class_name
        class_code = class_request.class_code
        
        if not class_name or not class_code:
            raise ValueError("Class name and code are required for registration")
        
        log.info(f"Registering class: {class_name}")
        
        # Execute class code to get class definition
        # Import endpoint decorator for class execution
        from endpoint import endpoint
        
        namespace: Dict[str, Any] = {
            'endpoint': endpoint,  # Make endpoint decorator available
        }
        exec(class_code, namespace)
        
        if class_name not in namespace:
            raise ValueError(f"Class '{class_name}' not found in provided code")
        
        cls = namespace[class_name]
        
        # Scan for @endpoint decorated methods
        endpoint_methods = self._scan_endpoint_methods(cls)
        
        # Store class information
        class_info = {
            'class_name': class_name,
            'class_code': class_code,
            'class_obj': cls,
            'dependencies': class_request.dependencies or [],
            'system_dependencies': class_request.system_dependencies or [],
            'endpoints': endpoint_methods,
            'registered_at': datetime.now().isoformat()
        }
        
        self.deployed_classes[class_name] = class_info
        
        log.info(f"Registered class {class_name} with {len(endpoint_methods)} HTTP endpoints")
        log.debug(f"Endpoint methods: {[ep['method_name'] for ep in endpoint_methods]}")
        
        return class_info
    
    def _scan_endpoint_methods(self, cls: Type) -> List[Dict[str, Any]]:
        """
        Scan class for methods decorated with @endpoint.
        
        Args:
            cls: Class to scan
            
        Returns:
            List of endpoint method information
        """
        endpoint_methods = []
        
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if hasattr(method, '_endpoint_config'):
                endpoint_config = method._endpoint_config
                
                endpoint_info = {
                    'method_name': name,
                    'http_methods': endpoint_config.get('methods', ['POST']),
                    'route': endpoint_config.get('route', f"/{name}"),
                    'function': method
                }
                
                endpoint_methods.append(endpoint_info)
                
                log.debug(f"Found endpoint method: {name} -> {endpoint_config}")
        
        return endpoint_methods
    
    async def execute_method(
        self, 
        class_name: str, 
        method_name: str, 
        request_data: Dict[str, Any]
    ) -> Any:
        """
        Execute a class method (either regular or endpoint method).
        
        Args:
            class_name: Name of the class
            method_name: Name of the method to execute
            request_data: Request data (from HTTP request or remote call)
            
        Returns:
            Method execution result
        """
        if class_name not in self.deployed_classes:
            raise ValueError(f"Class '{class_name}' is not registered")
        
        class_info = self.deployed_classes[class_name]
        cls = class_info['class_obj']
        
        # Get or create class instance
        instance = await self._get_or_create_instance(class_name, cls)
        
        # Get method
        if not hasattr(instance, method_name):
            raise ValueError(f"Method '{method_name}' not found in class '{class_name}'")
        
        method = getattr(instance, method_name)
        
        # Execute method
        try:
            log.debug(f"Executing {class_name}.{method_name} with data: {request_data}")
            
            # For HTTP calls, pass request data as keyword arguments
            if isinstance(request_data, dict):
                result = method(**request_data)
            else:
                result = method(request_data)
            
            # Update instance metadata
            self._update_instance_metadata(class_name)
            
            return result
            
        except Exception as e:
            log.error(f"Method execution failed for {class_name}.{method_name}: {e}")
            raise RuntimeError(f"Method execution failed: {str(e)}")
    
    async def execute_class_method(self, request: FunctionRequest) -> Any:
        """
        Execute a class method via FunctionRequest (for remote execution).
        
        Args:
            request: FunctionRequest containing method execution details
            
        Returns:
            Method execution result
        """
        class_name = request.class_name
        method_name = request.method_name
        
        # First ensure the class is registered
        if class_name not in self.deployed_classes:
            await self.register_class(request)
        
        class_info = self.deployed_classes[class_name]
        cls = class_info['class_obj']
        
        # Get or create instance with constructor args
        instance = await self._get_or_create_instance_with_constructor(
            class_name, cls, request
        )
        
        # Get method
        if not hasattr(instance, method_name):
            raise ValueError(f"Method '{method_name}' not found in class '{class_name}'")
        
        method = getattr(instance, method_name)
        
        # Deserialize arguments
        args = SerializationUtils.deserialize_args(request.args or [])
        kwargs = SerializationUtils.deserialize_kwargs(request.kwargs or {})
        
        # Execute method
        try:
            log.debug(f"Executing {class_name}.{method_name} via remote execution")
            
            result = method(*args, **kwargs)
            
            # Update instance metadata
            self._update_instance_metadata(class_name)
            
            return result
            
        except Exception as e:
            log.error(f"Remote method execution failed for {class_name}.{method_name}: {e}")
            raise RuntimeError(f"Remote method execution failed: {str(e)}")
    
    async def _get_or_create_instance(self, class_name: str, cls: Type) -> Any:
        """Get existing or create new class instance (no constructor args)."""
        
        instance_key = f"{class_name}_default"
        
        if instance_key in self.class_instances:
            log.debug(f"Using existing instance: {instance_key}")
            return self.class_instances[instance_key]
        
        # Create new instance with no constructor args
        log.info(f"Creating new instance of {class_name}")
        instance = cls()
        
        # Store instance and metadata
        self.class_instances[instance_key] = instance
        self.instance_metadata[instance_key] = {
            'class_name': class_name,
            'instance_id': instance_key,
            'created_at': datetime.now().isoformat(),
            'method_calls': 0,
            'last_used': datetime.now().isoformat()
        }
        
        return instance
    
    async def _get_or_create_instance_with_constructor(
        self, 
        class_name: str, 
        cls: Type, 
        request: FunctionRequest
    ) -> Any:
        """Get or create instance with constructor arguments."""
        
        instance_id = request.instance_id or f"{class_name}_{uuid.uuid4().hex[:8]}"
        
        # Check if we should reuse existing instance
        if (not request.create_new_instance and 
            instance_id in self.class_instances):
            log.debug(f"Reusing existing instance: {instance_id}")
            return self.class_instances[instance_id]
        
        # Create new instance with constructor args
        log.info(f"Creating new instance of {class_name} with ID: {instance_id}")
        
        # Deserialize constructor arguments
        constructor_args = SerializationUtils.deserialize_args(
            request.constructor_args or []
        )
        constructor_kwargs = SerializationUtils.deserialize_kwargs(
            request.constructor_kwargs or {}
        )
        
        # Create instance
        instance = cls(*constructor_args, **constructor_kwargs)
        
        # Store instance and metadata
        self.class_instances[instance_id] = instance
        self.instance_metadata[instance_id] = {
            'class_name': class_name,
            'instance_id': instance_id,
            'created_at': datetime.now().isoformat(),
            'method_calls': 0,
            'last_used': datetime.now().isoformat()
        }
        
        return instance
    
    def _update_instance_metadata(self, instance_key: str):
        """Update metadata for an instance."""
        if instance_key in self.instance_metadata:
            self.instance_metadata[instance_key]['method_calls'] += 1
            self.instance_metadata[instance_key]['last_used'] = datetime.now().isoformat()
        
        # Also update by class name for default instances
        for key, metadata in self.instance_metadata.items():
            if metadata.get('class_name') == instance_key:
                metadata['method_calls'] += 1
                metadata['last_used'] = datetime.now().isoformat()
    
    def get_registered_classes(self) -> List[str]:
        """Get list of registered class names."""
        return list(self.deployed_classes.keys())
    
    def get_class_endpoints(self, class_name: str) -> List[Dict[str, Any]]:
        """Get HTTP endpoints for a specific class."""
        if class_name not in self.deployed_classes:
            return []
        return self.deployed_classes[class_name]['endpoints']
    
    def get_instance_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific instance."""
        return self.instance_metadata.get(instance_id)
    
    def cleanup_instances(self, max_idle_minutes: int = 60):
        """Cleanup idle instances (future enhancement)."""
        # TODO: Implement instance cleanup based on idle time
        pass