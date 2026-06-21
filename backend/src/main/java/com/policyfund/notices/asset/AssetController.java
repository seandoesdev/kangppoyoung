package com.policyfund.notices.asset;

import com.policyfund.common.error.BadRequestException;
import com.policyfund.common.error.ResourceNotFoundException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.UncheckedIOException;

@RestController
@RequestMapping("/api/v1/notices/assets")
public class AssetController {

    private final AssetStorage storage;
    private final long maxImageBytes;

    public AssetController(AssetStorage storage,
                          @Value("${app.assets.max-image-bytes:10485760}") long maxImageBytes) {
        this.storage = storage;
        this.maxImageBytes = maxImageBytes;
    }

    @GetMapping("/{id}")
    public ResponseEntity<byte[]> asset(@PathVariable String id) {
        return storage.load(id)
                .map(bytes -> ResponseEntity.ok().contentType(MediaType.IMAGE_PNG).body(bytes))
                .orElseThrow(() -> new ResourceNotFoundException("ASSET_NOT_FOUND",
                        "자산을 찾을 수 없습니다: " + id));
    }

    /**
     * 검토 단계에서 수동 추가하는 이미지를 콘텐츠 주소 자산으로 업로드한다.
     * 전처리 산출 이미지와 동일하게 /api/v1/notices/assets/{id} 로 서빙되어 diff 동등성 규칙을 공유한다.
     */
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public AssetRef upload(@RequestParam("file") MultipartFile file) {
        byte[] raw;
        try {
            raw = file.getBytes();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
        if (raw.length == 0) {
            throw new BadRequestException("EMPTY_FILE", "빈 파일입니다.");
        }
        if (raw.length > maxImageBytes) {
            throw new BadRequestException("FILE_TOO_LARGE", "이미지 파일이 너무 큽니다.");
        }
        String contentType = file.getContentType();
        if (contentType == null || !contentType.toLowerCase().startsWith("image/")) {
            throw new BadRequestException("INVALID_FILE_TYPE", "이미지 파일만 업로드할 수 있습니다.");
        }
        String id = storage.storeImage(raw);
        return new AssetRef(id, "/api/v1/notices/assets/" + id);
    }
}
