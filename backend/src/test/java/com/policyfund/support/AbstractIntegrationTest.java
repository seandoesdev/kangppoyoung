package com.policyfund.support;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;
import org.testcontainers.containers.MySQLContainer;

/**
 * 통합 테스트 베이스. Testcontainers MySQL 컨테이너를 띄우고 datasource 를 동적 주입한다.
 *
 * 싱글톤 컨테이너 패턴: 컨테이너를 static 블록에서 한 번 start 하여 모든 통합 테스트
 * 클래스가 공유한다. @Container/@Testcontainers 라이프사이클(클래스 종료 시 stop)을
 * 쓰지 않으므로, 여러 통합 테스트 클래스를 한 JVM 에서 실행할 때 첫 클래스 종료 후
 * 컨테이너가 멈춰 다음 클래스가 중지된 컨테이너를 재사용하는 문제가 없다.
 * 컨테이너는 JVM 종료 시 Ryuk 가 정리한다.
 *
 * Docker 연결은 머신의 앰비언트 설정(Docker context / DOCKER_HOST)을 그대로 사용한다.
 * 특정 머신에서 연결 방식을 바꿔야 하면 커밋하지 않는 ~/.testcontainers.properties
 * 또는 셸 환경변수(DOCKER_HOST)로 주입한다(레포에 머신 종속 설정을 넣지 않는다).
 */
// 통합 테스트는 키 없이(오프라인 제공자) 돌도록 검색 provider 를 고정한다.
// 레포 기본값은 openai(실키 필요)이므로, 테스트에서는 hash/offline 로 핀.
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestPropertySource(properties = {
        "search.embedding.provider=hash",
        "search.synth.provider=offline"
})
public abstract class AbstractIntegrationTest {

    public static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0")
            .withDatabaseName("policyfund");

    static {
        MYSQL.start();
    }

    @DynamicPropertySource
    static void datasourceProps(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
    }
}
