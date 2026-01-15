from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

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
    def __init__(
        self,
        results_json: _Optional[str] = ...,
        success: bool = ...,
        error: _Optional[str] = ...,
    ) -> None: ...

class SearchRequest(_message.Message):
    __slots__ = ("keyword", "limit")
    KEYWORD_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    keyword: str
    limit: int
    def __init__(
        self, keyword: _Optional[str] = ..., limit: _Optional[int] = ...
    ) -> None: ...

class SearchResponse(_message.Message):
    __slots__ = ("results_json", "success", "error")
    RESULTS_JSON_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    results_json: str
    success: bool
    error: str
    def __init__(
        self,
        results_json: _Optional[str] = ...,
        success: bool = ...,
        error: _Optional[str] = ...,
    ) -> None: ...

class SemanticSearchRequest(_message.Message):
    __slots__ = ("query", "limit", "filter_tags", "filter_pages")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    FILTER_TAGS_FIELD_NUMBER: _ClassVar[int]
    FILTER_PAGES_FIELD_NUMBER: _ClassVar[int]
    query: str
    limit: int
    filter_tags: _containers.RepeatedScalarFieldContainer[str]
    filter_pages: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        query: _Optional[str] = ...,
        limit: _Optional[int] = ...,
        filter_tags: _Optional[_Iterable[str]] = ...,
        filter_pages: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class SemanticSearchResponse(_message.Message):
    __slots__ = ("results_json", "success", "error")
    RESULTS_JSON_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    results_json: str
    success: bool
    error: str
    def __init__(
        self,
        results_json: _Optional[str] = ...,
        success: bool = ...,
        error: _Optional[str] = ...,
    ) -> None: ...

class HybridSearchRequest(_message.Message):
    __slots__ = (
        "query",
        "limit",
        "filter_tags",
        "filter_pages",
        "fusion_method",
        "semantic_weight",
        "keyword_weight",
    )
    QUERY_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    FILTER_TAGS_FIELD_NUMBER: _ClassVar[int]
    FILTER_PAGES_FIELD_NUMBER: _ClassVar[int]
    FUSION_METHOD_FIELD_NUMBER: _ClassVar[int]
    SEMANTIC_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    KEYWORD_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    query: str
    limit: int
    filter_tags: _containers.RepeatedScalarFieldContainer[str]
    filter_pages: _containers.RepeatedScalarFieldContainer[str]
    fusion_method: str
    semantic_weight: float
    keyword_weight: float
    def __init__(
        self,
        query: _Optional[str] = ...,
        limit: _Optional[int] = ...,
        filter_tags: _Optional[_Iterable[str]] = ...,
        filter_pages: _Optional[_Iterable[str]] = ...,
        fusion_method: _Optional[str] = ...,
        semantic_weight: _Optional[float] = ...,
        keyword_weight: _Optional[float] = ...,
    ) -> None: ...

class HybridSearchResponse(_message.Message):
    __slots__ = ("results_json", "success", "error")
    RESULTS_JSON_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    results_json: str
    success: bool
    error: str
    def __init__(
        self,
        results_json: _Optional[str] = ...,
        success: bool = ...,
        error: _Optional[str] = ...,
    ) -> None: ...

class ReadPageRequest(_message.Message):
    __slots__ = ("page_name",)
    PAGE_NAME_FIELD_NUMBER: _ClassVar[int]
    page_name: str
    def __init__(self, page_name: _Optional[str] = ...) -> None: ...

class ReadPageResponse(_message.Message):
    __slots__ = ("success", "error", "content")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    content: str
    def __init__(
        self,
        success: bool = ...,
        error: _Optional[str] = ...,
        content: _Optional[str] = ...,
    ) -> None: ...

class ProposeChangeRequest(_message.Message):
    __slots__ = ("target_page", "content", "title", "description")
    TARGET_PAGE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    target_page: str
    content: str
    title: str
    description: str
    def __init__(
        self,
        target_page: _Optional[str] = ...,
        content: _Optional[str] = ...,
        title: _Optional[str] = ...,
        description: _Optional[str] = ...,
    ) -> None: ...

class ProposeChangeResponse(_message.Message):
    __slots__ = ("success", "error", "proposal_path", "is_new_page", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    PROPOSAL_PATH_FIELD_NUMBER: _ClassVar[int]
    IS_NEW_PAGE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    proposal_path: str
    is_new_page: bool
    message: str
    def __init__(
        self,
        success: bool = ...,
        error: _Optional[str] = ...,
        proposal_path: _Optional[str] = ...,
        is_new_page: bool = ...,
        message: _Optional[str] = ...,
    ) -> None: ...

class ListProposalsRequest(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: str
    def __init__(self, status: _Optional[str] = ...) -> None: ...

class ProposalInfo(_message.Message):
    __slots__ = (
        "path",
        "target_page",
        "title",
        "description",
        "status",
        "is_new_page",
        "proposed_by",
        "created_at",
    )
    PATH_FIELD_NUMBER: _ClassVar[int]
    TARGET_PAGE_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    IS_NEW_PAGE_FIELD_NUMBER: _ClassVar[int]
    PROPOSED_BY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    path: str
    target_page: str
    title: str
    description: str
    status: str
    is_new_page: bool
    proposed_by: str
    created_at: str
    def __init__(
        self,
        path: _Optional[str] = ...,
        target_page: _Optional[str] = ...,
        title: _Optional[str] = ...,
        description: _Optional[str] = ...,
        status: _Optional[str] = ...,
        is_new_page: bool = ...,
        proposed_by: _Optional[str] = ...,
        created_at: _Optional[str] = ...,
    ) -> None: ...

class ListProposalsResponse(_message.Message):
    __slots__ = ("success", "error", "count", "proposals")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    PROPOSALS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    count: int
    proposals: _containers.RepeatedCompositeFieldContainer[ProposalInfo]
    def __init__(
        self,
        success: bool = ...,
        error: _Optional[str] = ...,
        count: _Optional[int] = ...,
        proposals: _Optional[_Iterable[_Union[ProposalInfo, _Mapping]]] = ...,
    ) -> None: ...

class WithdrawProposalRequest(_message.Message):
    __slots__ = ("proposal_path",)
    PROPOSAL_PATH_FIELD_NUMBER: _ClassVar[int]
    proposal_path: str
    def __init__(self, proposal_path: _Optional[str] = ...) -> None: ...

class WithdrawProposalResponse(_message.Message):
    __slots__ = ("success", "error", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    message: str
    def __init__(
        self,
        success: bool = ...,
        error: _Optional[str] = ...,
        message: _Optional[str] = ...,
    ) -> None: ...

class GetFolderContextRequest(_message.Message):
    __slots__ = ("folder_path",)
    FOLDER_PATH_FIELD_NUMBER: _ClassVar[int]
    folder_path: str
    def __init__(self, folder_path: _Optional[str] = ...) -> None: ...

class GetFolderContextResponse(_message.Message):
    __slots__ = (
        "success",
        "error",
        "found",
        "page_name",
        "page_content",
        "folder_scope",
    )
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    FOUND_FIELD_NUMBER: _ClassVar[int]
    PAGE_NAME_FIELD_NUMBER: _ClassVar[int]
    PAGE_CONTENT_FIELD_NUMBER: _ClassVar[int]
    FOLDER_SCOPE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    found: bool
    page_name: str
    page_content: str
    folder_scope: str
    def __init__(
        self,
        success: bool = ...,
        error: _Optional[str] = ...,
        found: bool = ...,
        page_name: _Optional[str] = ...,
        page_content: _Optional[str] = ...,
        folder_scope: _Optional[str] = ...,
    ) -> None: ...

class GetProjectContextRequest(_message.Message):
    __slots__ = ("github_remote", "folder_path")
    GITHUB_REMOTE_FIELD_NUMBER: _ClassVar[int]
    FOLDER_PATH_FIELD_NUMBER: _ClassVar[int]
    github_remote: str
    folder_path: str
    def __init__(
        self, github_remote: _Optional[str] = ..., folder_path: _Optional[str] = ...
    ) -> None: ...

class RelatedPage(_message.Message):
    __slots__ = ("name", "path")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    name: str
    path: str
    def __init__(
        self, name: _Optional[str] = ..., path: _Optional[str] = ...
    ) -> None: ...

class ProjectInfo(_message.Message):
    __slots__ = ("file", "github", "tags", "concerns", "content")
    FILE_FIELD_NUMBER: _ClassVar[int]
    GITHUB_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    CONCERNS_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    file: str
    github: str
    tags: _containers.RepeatedScalarFieldContainer[str]
    concerns: _containers.RepeatedScalarFieldContainer[str]
    content: str
    def __init__(
        self,
        file: _Optional[str] = ...,
        github: _Optional[str] = ...,
        tags: _Optional[_Iterable[str]] = ...,
        concerns: _Optional[_Iterable[str]] = ...,
        content: _Optional[str] = ...,
    ) -> None: ...

class GetProjectContextResponse(_message.Message):
    __slots__ = ("success", "error", "project", "related_pages")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    PROJECT_FIELD_NUMBER: _ClassVar[int]
    RELATED_PAGES_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    project: ProjectInfo
    related_pages: _containers.RepeatedCompositeFieldContainer[RelatedPage]
    def __init__(
        self,
        success: bool = ...,
        error: _Optional[str] = ...,
        project: _Optional[_Union[ProjectInfo, _Mapping]] = ...,
        related_pages: _Optional[_Iterable[_Union[RelatedPage, _Mapping]]] = ...,
    ) -> None: ...
