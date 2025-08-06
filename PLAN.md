 Stdout Feedback Enhancement Implementation Plan

## Overview

This document outlines comprehensive implementation plans for enhancing the stdout feedback feature in worker-tetra. The current implementation successfully captures and forwards stdout from remote functions to local development environments. These enhancements will improve the user experience, performance, and flexibility of the stdout feedback system.

## Current State Analysis

### Existing Implementation
- **Capture**: Complete stdout/stderr/log capture using `io.StringIO()` and `redirect_stdout/stderr`
- **Transport**: Stdout included in `FunctionResponse.stdout` field via JSON
- **Display**: Client logs with "Remote |" prefix using `log.info()`
- **Test Coverage**: Integration tests validate end-to-end stdout capture

### Architecture Components
- `src/function_executor.py` - Output capture logic
- `src/class_executor.py` - Class execution output capture  
- `src/remote_execution.py` - Protocol definitions
- `tetra-rp/src/tetra_rp/stubs/live_serverless.py` - Client-side processing

---

## Enhancement 1: Real-time Streaming

### Objective
Enable live streaming of stdout during function execution instead of batching until completion.

### Technical Implementation

#### Phase 1: Infrastructure Setup
```python
# New streaming protocol in remote_execution.py
class StreamingResponse(BaseModel):
    chunk_type: str = Field(description="'stdout', 'stderr', 'log', 'result', 'error'")
    content: str = Field(description="Chunk content")
    timestamp: float = Field(description="Unix timestamp")
    sequence: int = Field(description="Sequence number for ordering")
```

#### Phase 2: Worker-Side Streaming
```python
# Enhanced function_executor.py
class StreamingExecutor:
    def __init__(self, stream_callback):
        self.stream_callback = stream_callback
        self.sequence_counter = 0
    
    def _stream_output(self, chunk_type: str, content: str):
        """Send output chunk immediately to client"""
        chunk = StreamingResponse(
            chunk_type=chunk_type,
            content=content,
            timestamp=time.time(),
            sequence=self.sequence_counter
        )
        self.sequence_counter += 1
        self.stream_callback(chunk)
    
    class StreamingStringIO(io.StringIO):
        def write(self, s):
            super().write(s)
            self.executor._stream_output('stdout', s)
            return len(s)
```

#### Phase 3: Transport Layer
- **WebSocket Implementation**: Use WebSocket connections for bidirectional streaming
- **HTTP Streaming**: Alternative using Server-Sent Events (SSE) for HTTP-only environments
- **Buffer Management**: Implement client-side buffering for out-of-order chunks

#### Phase 4: Client Integration
```python
# Enhanced live_serverless.py
class StreamingClient:
    def __init__(self):
        self.output_buffer = []
        self.completion_handlers = {}
    
    async def stream_function_execution(self, request):
        async with websockets.connect(self.endpoint_url) as websocket:
            await websocket.send(request.model_dump_json())
            
            async for message in websocket:
                chunk = StreamingResponse.model_validate_json(message)
                await self._handle_stream_chunk(chunk)
    
    async def _handle_stream_chunk(self, chunk):
        if chunk.chunk_type in ['stdout', 'stderr', 'log']:
            log.info(f"Remote | {chunk.content}")
        elif chunk.chunk_type == 'result':
            return self._deserialize_result(chunk.content)
```

### Performance Considerations
- **Latency**: ~10-50ms improvement in feedback latency
- **Bandwidth**: Slight increase due to chunk overhead (~5-10%)
- **Memory**: Reduced server-side memory usage for long-running functions
- **Scalability**: Better handling of concurrent executions with immediate feedback

### Migration Strategy
1. **Backward Compatibility**: Maintain existing batch mode as default
2. **Feature Flag**: `streaming=True` parameter in `@remote` decorator
3. **Gradual Rollout**: Enable streaming for specific function types first
4. **Fallback**: Automatic fallback to batch mode if streaming fails

---

## Enhancement 2: Colored Output

### Objective
Preserve ANSI color codes and terminal formatting in stdout display.

### Technical Implementation

#### Phase 1: Color Detection and Preservation
```python
# New color handling in function_executor.py
import re
import sys

class ColorAwareStringIO(io.StringIO):
    ANSI_COLOR_PATTERN = re.compile(r'\x1b\[[0-9;]*m')
    
    def __init__(self, supports_color=True):
        super().__init__()
        self.supports_color = supports_color
        self.color_enabled = supports_color and sys.stdout.isatty()
    
    def write(self, s):
        if self.color_enabled:
            # Preserve ANSI codes
            super().write(s)
        else:
            # Strip ANSI codes for non-terminal output
            clean_s = self.ANSI_COLOR_PATTERN.sub('', s)
            super().write(clean_s)
        return len(s)
```

#### Phase 2: Cross-Platform Color Support
```python
# Enhanced color handling
class ColorManager:
    def __init__(self):
        self.colorama_available = self._check_colorama()
        self.terminal_capabilities = self._detect_terminal()
    
    def _check_colorama(self):
        try:
            import colorama
            colorama.init()
            return True
        except ImportError:
            return False
    
    def _detect_terminal(self):
        """Detect terminal color capabilities"""
        return {
            'supports_256_colors': os.environ.get('TERM', '').find('256') != -1,
            'supports_truecolor': os.environ.get('COLORTERM') in ['truecolor', '24bit'],
            'is_tty': sys.stdout.isatty()
        }
    
    def process_colored_output(self, text: str) -> str:
        """Process colored output based on terminal capabilities"""
        if not self.terminal_capabilities['is_tty']:
            return self._strip_colors(text)
        
        if self.colorama_available:
            return text  # Colorama handles cross-platform
        else:
            return self._convert_colors(text)
```

#### Phase 3: Client-Side Color Rendering
```python
# Enhanced client output in live_serverless.py
class ColoredOutputHandler:
    def __init__(self):
        self.color_manager = ColorManager()
    
    def display_remote_output(self, content: str, chunk_type: str = 'stdout'):
        # Add color coding based on chunk type
        prefix_colors = {
            'stdout': '\033[32m',  # Green
            'stderr': '\033[31m',  # Red  
            'log': '\033[33m',     # Yellow
        }
        
        reset_color = '\033[0m'
        prefix_color = prefix_colors.get(chunk_type, '')
        
        processed_content = self.color_manager.process_colored_output(content)
        
        for line in processed_content.splitlines():
            colored_output = f"{prefix_color}Remote | {reset_color}{line}"
            log.info(colored_output)
```

#### Phase 4: Configuration Options
```python
# Configuration in constants.py
COLOR_CONFIG = {
    'enable_colors': True,
    'preserve_ansi': True,
    'prefix_colors': {
        'stdout': 'green',
        'stderr': 'red',
        'log': 'yellow'
    },
    'force_colors': False,  # Force colors even in non-TTY
    'color_scheme': 'default'  # 'default', 'dark', 'light'
}
```

### Testing Strategy
- **Color Preservation Tests**: Verify ANSI codes survive round-trip
- **Cross-Platform Tests**: Test on Windows, macOS, Linux terminals
- **Fallback Tests**: Verify graceful degradation without color support
- **Performance Tests**: Measure color processing overhead

---

## Enhancement 5: Progress Indicators

### Objective
Preserve and enhance display of progress bars and interactive terminal elements.

### Technical Implementation

#### Phase 1: Progress Detection and Preservation
```python
# Progress bar detection in function_executor.py
class ProgressAwareStringIO(io.StringIO):
    PROGRESS_PATTERNS = [
        re.compile(r'.*\d+%.*'),  # Percentage indicators
        re.compile(r'.*\[#+.*\].*'),  # Bar indicators [####    ]
        re.compile(r'.*\r.*'),  # Carriage return (overwriting lines)
        re.compile(r'.*\x1b\[\d+[ABCD].*'),  # ANSI cursor movement
    ]
    
    def __init__(self):
        super().__init__()
        self.is_progress_line = False
        self.last_progress_content = ""
    
    def write(self, s):
        super().write(s)
        
        # Detect if this is a progress indicator
        self.is_progress_line = any(pattern.search(s) for pattern in self.PROGRESS_PATTERNS)
        
        if self.is_progress_line:
            self.last_progress_content = s
            self._handle_progress_update(s)
        
        return len(s)
    
    def _handle_progress_update(self, content):
        """Handle progress bar updates with special processing"""
        # Send progress updates with special markup
        chunk = StreamingResponse(
            chunk_type='progress',
            content=content,
            timestamp=time.time(),
            sequence=self.sequence_counter
        )
        self.stream_callback(chunk)
```

#### Phase 2: Interactive Element Support
```python
# Enhanced progress handling
class InteractiveElementHandler:
    def __init__(self):
        self.terminal_state = {
            'cursor_position': (0, 0),
            'screen_buffer': [],
            'supports_cursor_control': self._detect_cursor_support()
        }
    
    def _detect_cursor_support(self) -> bool:
        """Detect if terminal supports cursor positioning"""
        return (
            sys.stdout.isatty() and 
            os.environ.get('TERM', '').lower() not in ['dumb', 'unknown']
        )
    
    def process_interactive_content(self, content: str) -> str:
        """Process content with interactive elements"""
        if '\r' in content and not content.endswith('\n'):
            # Handle carriage return (overwriting current line)
            return self._handle_carriage_return(content)
        elif '\x1b[' in content:
            # Handle ANSI escape sequences
            return self._handle_ansi_sequences(content)
        else:
            return content
    
    def _handle_carriage_return(self, content: str) -> str:
        """Handle carriage return for progress bars"""
        if self.terminal_state['supports_cursor_control']:
            # Preserve carriage return for compatible terminals
            return content
        else:
            # Convert to newline for non-compatible terminals
            return content.replace('\r', '\n')
    
    def _handle_ansi_sequences(self, content: str) -> str:
        """Process ANSI escape sequences for cursor control"""
        ansi_pattern = re.compile(r'\x1b\[(\d*)(A|B|C|D|H|J|K)')
        
        def replace_ansi(match):
            num = match.group(1) or '1'
            command = match.group(2)
            
            if not self.terminal_state['supports_cursor_control']:
                # Strip unsupported ANSI codes
                return ''
            return match.group(0)  # Keep original
        
        return ansi_pattern.sub(replace_ansi, content)
```

#### Phase 3: Progress Bar Library Integration
```python
# Special handling for common progress libraries
class ProgressLibraryAdapter:
    """Adapter for common progress bar libraries"""
    
    SUPPORTED_LIBRARIES = {
        'tqdm': {
            'detection_pattern': r'.*\d+%\|.*\|.*',
            'update_pattern': r'\r.*\d+%\|.*\|.*'
        },
        'progressbar2': {
            'detection_pattern': r'.*\[#+.*\].*\d+%.*',
            'update_pattern': r'\r.*\[#+.*\].*'
        },
        'rich': {
            'detection_pattern': r'.*\x1b\[.*Progress.*',
            'update_pattern': r'.*\x1b\[.*'
        }
    }
    
    def __init__(self):
        self.detected_library = None
        self.progress_state = {}
    
    def detect_progress_library(self, content: str) -> Optional[str]:
        """Detect which progress library is being used"""
        for lib_name, patterns in self.SUPPORTED_LIBRARIES.items():
            if re.search(patterns['detection_pattern'], content):
                self.detected_library = lib_name
                return lib_name
        return None
    
    def process_progress_update(self, content: str) -> dict:
        """Extract progress information from library-specific format"""
        if self.detected_library == 'tqdm':
            return self._parse_tqdm_progress(content)
        elif self.detected_library == 'progressbar2':
            return self._parse_progressbar2_progress(content)
        elif self.detected_library == 'rich':
            return self._parse_rich_progress(content)
        return {'raw': content}
    
    def _parse_tqdm_progress(self, content: str) -> dict:
        """Parse tqdm progress format"""
        # Extract: percentage, rate, eta, etc.
        match = re.search(r'(\d+)%\|.*\|\s*(\d+/\d+).*\[(.*?)<(.*?),\s*(.*?)\]', content)
        if match:
            return {
                'percentage': int(match.group(1)),
                'progress': match.group(2),
                'elapsed': match.group(3),
                'eta': match.group(4),
                'rate': match.group(5),
                'raw': content
            }
        return {'raw': content}
```

#### Phase 4: Client-Side Progress Display
```python
# Enhanced client progress display
class ProgressDisplayManager:
    def __init__(self):
        self.active_progress_bars = {}
        self.progress_adapter = ProgressLibraryAdapter()
    
    def handle_progress_chunk(self, chunk: StreamingResponse):
        """Handle progress-specific chunks"""
        content = chunk.content
        
        # Detect progress library if not already known
        if not self.progress_adapter.detected_library:
            detected = self.progress_adapter.detect_progress_library(content)
            if detected:
                log.debug(f"Detected progress library: {detected}")
        
        # Process progress update
        progress_info = self.progress_adapter.process_progress_update(content)
        
        if 'percentage' in progress_info:
            self._display_structured_progress(progress_info)
        else:
            self._display_raw_progress(content)
    
    def _display_structured_progress(self, progress_info: dict):
        """Display structured progress information"""
        percentage = progress_info['percentage']
        rate = progress_info.get('rate', '')
        eta = progress_info.get('eta', '')
        
        # Create clean progress display
        progress_line = f"Remote Progress: {percentage}% | {rate} | ETA: {eta}"
        
        # Use carriage return to overwrite previous progress line
        if sys.stdout.isatty():
            print(f"\r{progress_line}", end='', flush=True)
        else:
            # For non-TTY, print periodic updates
            if percentage % 10 == 0:  # Every 10%
                log.info(progress_line)
    
    def _display_raw_progress(self, content: str):
        """Display raw progress content with minimal processing"""
        processed_content = self.interactive_handler.process_interactive_content(content)
        log.info(f"Remote | {processed_content}")
```

### Configuration Options
```python
# Progress display configuration
class ProgressConfig(BaseModel):
    enable_progress_detection: bool = Field(default=True)
    preserve_ansi_progress: bool = Field(default=True)
    convert_to_structured: bool = Field(default=True)
    update_frequency: int = Field(default=1, description="Update every N percent")
    libraries: List[str] = Field(default=['tqdm', 'progressbar2', 'rich'])
```

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] Implement basic streaming infrastructure
- [ ] Add color detection and preservation
- [ ] Create configuration system for prefixes
- [ ] Set up filter framework

### Phase 2: Core Features (Weeks 3-4) 
- [ ] Complete streaming implementation
- [ ] Implement configurable prefix templates
- [ ] Build filter engine with common presets
- [ ] Add basic progress detection

### Phase 3: Advanced Features (Weeks 5-6)
- [ ] Progress bar library integration
- [ ] Advanced color management
- [ ] Performance optimizations
- [ ] Comprehensive testing

### Phase 4: Polish & Documentation (Weeks 7-8)
- [ ] User documentation
- [ ] Migration guides
- [ ] Performance benchmarking
- [ ] Integration examples

## Testing Strategy

### Unit Tests
- Color code preservation
- Filter pattern matching
- Template rendering
- Progress detection

### Integration Tests
- End-to-end streaming
- Cross-platform compatibility
- Library compatibility (tqdm, rich, etc.)
- Performance under load

### User Acceptance Tests
- Real-world usage scenarios
- Developer experience validation
- Configuration usability
- Error handling

## Performance Considerations

### Streaming Enhancement
- **Memory**: Reduced by ~30-50% for long-running functions
- **Latency**: Improved by ~10-50ms for first output
- **CPU**: Slight increase (~5-10%) due to chunking overhead

### Filtering Enhancement
- **Regex Compilation**: One-time cost at initialization
- **Filter Performance**: O(n*f) where n=output lines, f=filter count
- **Memory Impact**: Minimal, filters process line-by-line

### Color Enhancement
- **Processing Overhead**: ~2-5ms per colored line
- **Memory**: Minimal additional usage
- **Compatibility**: Graceful degradation on unsupported terminals

## Migration and Compatibility

### Backward Compatibility
- All enhancements are opt-in via configuration
- Existing functionality remains unchanged
- Default behavior matches current implementation

### Migration Path
1. **Silent Rollout**: Deploy with features disabled by default
2. **Opt-in Beta**: Allow early adopters to enable features
3. **Gradual Default**: Enable features by default over time
4. **Legacy Support**: Maintain old behavior for specified period

## Conclusion

These enhancements will significantly improve the developer experience when working with remote functions, providing real-time feedback, better visual presentation, and flexible control over output display. The modular design ensures each enhancement can be implemented and deployed independently, reducing risk and allowing for iterative improvement based on user feedback.
