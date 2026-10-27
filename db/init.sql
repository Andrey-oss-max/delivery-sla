-- Схема базы delivery_sla (MySQL 8.4). Скрипт идемпотентен: повторный запуск ничего не дублирует.
-- Применяется автоматически при первом старте контейнера db и командой: python -m sla.cli init

CREATE TABLE IF NOT EXISTS zone (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    code          VARCHAR(8)   NOT NULL UNIQUE,
    name          VARCHAR(64)  NOT NULL,
    express_hours TINYINT UNSIGNED NOT NULL,
    standard_days TINYINT UNSIGNED NOT NULL,
    CHECK (express_hours BETWEEN 1 AND 72),
    CHECK (standard_days BETWEEN 1 AND 10)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS holiday (
    day  DATE        NOT NULL PRIMARY KEY,
    name VARCHAR(64) NOT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS import_batch (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    source    VARCHAR(255) NOT NULL,
    kind      ENUM('registry', 'simulate', 'api') NOT NULL,
    loaded_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    accepted  INT NULL,
    rejected  INT NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS orders (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    order_no      VARCHAR(32) NOT NULL UNIQUE,
    channel       ENUM('site', 'marketplace', 'phone') NOT NULL,
    zone_id       INT         NOT NULL,
    tariff        ENUM('express', 'standard') NOT NULL,
    created_at    DATETIME    NOT NULL,
    delivered_at  DATETIME    NULL,
    status        ENUM('delivered', 'in_transit', 'cancelled') NOT NULL,
    reschedule_to DATETIME    NULL,
    batch_id      INT         NULL,
    CONSTRAINT fk_orders_zone  FOREIGN KEY (zone_id)  REFERENCES zone (id),
    CONSTRAINT fk_orders_batch FOREIGN KEY (batch_id) REFERENCES import_batch (id) ON DELETE SET NULL,
    INDEX ix_orders_created (created_at)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sla_result (
    order_id    INT          NOT NULL PRIMARY KEY,
    deadline    DATETIME     NOT NULL,
    outcome     ENUM('on_time', 'late', 'open_late', 'in_progress', 'excluded') NOT NULL,
    hours       DECIMAL(7,2) NULL,
    delay_h     DECIMAL(7,2) NULL,
    computed_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_result_order FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
    INDEX ix_result_deadline (deadline)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sla_daily (
    day         DATE         NOT NULL,
    zone_id     INT          NOT NULL,
    total       INT          NOT NULL,
    on_time     INT          NOT NULL,
    late        INT          NOT NULL,
    open_late   INT          NOT NULL,
    in_progress INT          NOT NULL,
    excluded    INT          NOT NULL,
    sla_pct     DECIMAL(4,1) NULL,
    p50_h       DECIMAL(7,2) NULL,
    p90_h       DECIMAL(7,2) NULL,
    PRIMARY KEY (day, zone_id),
    CONSTRAINT fk_daily_zone FOREIGN KEY (zone_id) REFERENCES zone (id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS rejected (
    id       INT AUTO_INCREMENT PRIMARY KEY,
    batch_id INT          NULL,
    line_no  INT          NOT NULL,
    order_no VARCHAR(64)  NOT NULL DEFAULT '',
    raw      TEXT         NOT NULL,
    reason   VARCHAR(500) NOT NULL,
    CONSTRAINT fk_rejected_batch FOREIGN KEY (batch_id) REFERENCES import_batch (id) ON DELETE SET NULL
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- начальные данные: зоны доставки Калининграда и праздничные дни 2026 года
INSERT IGNORE INTO zone (code, name, express_hours, standard_days) VALUES
    ('CTR', 'Центральный район', 3, 1),
    ('LEN', 'Ленинградский район', 4, 1),
    ('MOS', 'Московский район', 4, 1),
    ('PRG', 'Пригород', 6, 2),
    ('OBL', 'Калининградская область', 24, 3);

INSERT IGNORE INTO holiday (day, name) VALUES
    ('2026-01-01', 'Новогодние каникулы'), ('2026-01-02', 'Новогодние каникулы'),
    ('2026-01-05', 'Новогодние каникулы'), ('2026-01-06', 'Новогодние каникулы'),
    ('2026-01-07', 'Рождество Христово'), ('2026-01-08', 'Новогодние каникулы'),
    ('2026-01-09', 'Перенос выходного'), ('2026-02-23', 'День защитника Отечества'),
    ('2026-03-09', 'Международный женский день (перенос)'), ('2026-05-01', 'Праздник Весны и Труда'),
    ('2026-05-11', 'День Победы (перенос)'), ('2026-06-12', 'День России'),
    ('2026-11-04', 'День народного единства'), ('2026-12-31', 'Перенос выходного');
