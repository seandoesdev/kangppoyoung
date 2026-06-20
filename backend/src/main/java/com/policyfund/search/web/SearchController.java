package com.policyfund.search.web;

import com.policyfund.common.error.ResourceNotFoundException;
import com.policyfund.search.dto.SearchExample;
import com.policyfund.search.dto.SearchHistoryItem;
import com.policyfund.search.dto.SearchRequest;
import com.policyfund.search.dto.SearchResult;
import com.policyfund.search.service.SearchExampleService;
import com.policyfund.search.service.SearchService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/v1/search")
public class SearchController {

    private final SearchService service;
    private final SearchExampleService exampleService;

    public SearchController(SearchService service, SearchExampleService exampleService) {
        this.service = service;
        this.exampleService = exampleService;
    }

    @PostMapping
    public SearchResult search(@Valid @RequestBody SearchRequest request) {
        return service.search(request.query());
    }

    @GetMapping("/history")
    public List<SearchHistoryItem> history(
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.history(page, Math.min(size, 100));
    }

    @GetMapping("/history/{sessionId}")
    public SearchHistoryItem historyItem(@PathVariable String sessionId) {
        return service.bySession(sessionId)
                .orElseThrow(() -> new ResourceNotFoundException(
                        "HISTORY_NOT_FOUND", "검색 기록을 찾을 수 없습니다."));
    }

    @DeleteMapping("/history/{sessionId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteHistory(@PathVariable String sessionId) {
        service.deleteHistory(sessionId);
    }

    @DeleteMapping("/history")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void clearHistory() {
        service.clearHistory();
    }

    public record AddExampleRequest(@NotBlank String text) {}

    @GetMapping("/examples")
    public List<SearchExample> examples() {
        return exampleService.list();
    }

    @PostMapping("/examples")
    @ResponseStatus(HttpStatus.CREATED)
    public SearchExample addExample(@Valid @RequestBody AddExampleRequest req) {
        return exampleService.add(req.text());
    }

    @DeleteMapping("/examples/{exampleId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void deleteExample(@PathVariable String exampleId) {
        exampleService.delete(exampleId);
    }
}
