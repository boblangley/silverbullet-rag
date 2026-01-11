from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class QueryRequest(_message.Message):
    __slots__ = ("cypher_query",)
    CYPHER_QUERY_FIELD_NUMBER: _ClassVar[int]
    cypher_query: str
    def __init__(self, cypher_query: _Optional[str] = ...) -> None: ...

class QueryResponse(_message.Message):
    __slots__ = ("results_json", "success", "error")
    RESULTS_JSON_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    results_json: str
    success: bool
    error: str
    def __init__(self, results_json: _Optional[str] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class SearchRequest(_message.Message):
    __slots__ = ("keyword",)
    KEYWORD_FIELD_NUMBER: _ClassVar[int]
    keyword: str
    def __init__(self, keyword: _Optional[str] = ...) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("results_json", "success", "error")
    RESULTS_JSON_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    results_json: str
    success: bool
    error: str
    def __init__(self, results_json: _Optional[str] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class UpdatePageRequest(_message.Message):
    __slots__ = ("page_name", "content")
    PAGE_NAME_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    page_name: str
    content: str
    def __init__(self, page_name: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class UpdatePageResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...
