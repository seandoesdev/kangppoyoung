package com.policyfund.notices.asset;

import com.policyfund.common.error.BadRequestException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AssetStorageTest {

    @Test
    void store_isContentAddressed_sameBytesSameId(@TempDir Path tmp) {
        AssetStorage storage = new AssetStorage(tmp.toString());
        byte[] img = "PNGDATA".getBytes();

        String id1 = storage.store(img);
        String id2 = storage.store(img);

        assertThat(id1).isEqualTo(id2);
        Optional<byte[]> loaded = storage.load(id1);
        assertThat(loaded).isPresent();
        assertThat(loaded.get()).isEqualTo(img);
    }

    @Test
    void load_missing_returnsEmpty(@TempDir Path tmp) {
        AssetStorage storage = new AssetStorage(tmp.toString());
        assertThat(storage.load("deadbeef")).isEmpty();
    }

    @Test
    void storeImage_normalizesToPngAndStores(@TempDir Path tmp) throws Exception {
        AssetStorage storage = new AssetStorage(tmp.toString());
        java.awt.image.BufferedImage img =
                new java.awt.image.BufferedImage(2, 2, java.awt.image.BufferedImage.TYPE_INT_RGB);
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        javax.imageio.ImageIO.write(img, "png", out);

        String id = storage.storeImage(out.toByteArray());

        assertThat(id).matches("[0-9a-f]{64}");
        assertThat(storage.load(id)).isPresent();
    }

    @Test
    void storeImage_nonImage_throwsBadRequest(@TempDir Path tmp) {
        AssetStorage storage = new AssetStorage(tmp.toString());
        assertThatThrownBy(() -> storage.storeImage("not an image".getBytes()))
                .isInstanceOf(BadRequestException.class);
    }
}
