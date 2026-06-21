package com.policyfund.notices.asset;

import com.policyfund.common.error.BadRequestException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Optional;

/** 추출 이미지를 콘텐츠 주소(sha256)로 저장한다. 동일 이미지는 동일 id → diff 동등성(발견 #11). */
@Component
public class AssetStorage {

    private final Path dir;

    public AssetStorage(@Value("${app.assets.dir:./data/assets}") String dir) {
        this.dir = Path.of(dir);
    }

    public String store(byte[] bytes) {
        String id = sha256Hex(bytes);
        try {
            Files.createDirectories(dir);
            Path file = dir.resolve(id + ".png");
            if (!Files.exists(file)) {
                Files.write(file, bytes);
            }
            return id;
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /**
     * 업로드 이미지를 PNG 로 정규화해 콘텐츠 주소(sha256)로 저장한다. 동일 이미지 → 동일 id 라
     * 전처리 산출 이미지와 같은 diff 동등성 규칙을 따른다. 해석 불가하면 INVALID_FILE_TYPE.
     */
    public String storeImage(byte[] raw) {
        try {
            BufferedImage image = ImageIO.read(new ByteArrayInputStream(raw));
            if (image == null) {
                throw new BadRequestException("INVALID_FILE_TYPE", "이미지 파일만 업로드할 수 있습니다.");
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            ImageIO.write(image, "png", out);
            return store(out.toByteArray());
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    public Optional<byte[]> load(String id) {
        if (id == null || !id.matches("[0-9a-f]{64}")) {
            return Optional.empty();
        }
        Path file = dir.resolve(id + ".png");
        try {
            return Files.exists(file) ? Optional.of(Files.readAllBytes(file)) : Optional.empty();
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    private static String sha256Hex(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
