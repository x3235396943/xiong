from __future__ import annotations

import json
import random
import time
from typing import List, Set
from collections import deque
import threading

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin

from ..tools import log
from ..tools.config import get_config
from ..dyShare.crawler import ConcreteDyShareCrawler, DyShareUtils
from ..tools.douyin_common import (
    DouyinConfigParser,
    DouyinBrowserActions,
    DouyinCommentActions,
    parse_comment_dt,
    within_threshold,
)
from ..tools.core import DataReporter


class ConcreteDySearchCrawler(ConcreteDyShareCrawler):
    def __init__(self):
        super().__init__()
        self.utils = DyShareUtils()
        self.search_keywords: List[str] = []
        self.keyword_queue = deque()
        self._kw_lock = threading.Lock()
        self.keyword_processed: Set[str] = set()

    def _send_ws_message_for_reporter(self, message_dict):
        try:
            if (
                isinstance(message_dict, dict)
                and message_dict.get("cmd") == "PcDataReq"
            ):
                data = message_dict.get("data")
                if isinstance(data, dict):
                    data.pop("comment", None)
                    for k in ("urlIndex", "urlOk", "urlFail"):
                        data.pop(k, None)
        except Exception:
            pass
        self._send_ws_message(message_dict)

    def setup_database(self) -> None:
        cfg = get_config()
        if not cfg.BIT_BROWSER_IDS:
            raise Exception("请在 BIT_BROWSER_IDS 中至少配置一个浏览器ID")
        raw_keywords = getattr(cfg, "KEYWORDS", None)
        self.search_keywords = DouyinConfigParser.parse_keywords(raw_keywords or [])
        log.info(f"初始化 KEYWORDS 共 {len(self.search_keywords)} 项")
        with self._kw_lock:
            self.keyword_queue.clear()
            self.keyword_processed.clear()
            for kw in self.search_keywords:
                self.keyword_queue.append(kw)

    def _handle_config_update(self, config_data: dict):
        super()._handle_config_update(config_data)
        try:
            cfg = get_config()
            if "KEYWORDS" in config_data:
                updated = DouyinConfigParser.parse_keywords(cfg.KEYWORDS or [])
                with self._kw_lock:
                    added = 0
                    for kw in updated:
                        if (
                            kw not in self.keyword_processed
                            and kw not in self.keyword_queue
                        ):
                            self.keyword_queue.append(kw)
                            added += 1
                log.info(
                    f"KEYWORDS 已更新，新增 {added} 项，队列共 {len(self.keyword_queue)} 项"
                )
        except Exception as e:
            log.error(f"刷新 KEYWORDS 失败: {e}")

    def cleanup_resources(self) -> None:
        super().cleanup_resources()
        import sys

        sys.exit(0)

    def process_urls_with_thread_pool(self) -> None:
        MAX_WORKERS_USED = len(self.config.BIT_BROWSER_IDS)
        WAIT_TIME_USED = self.config.WAIT_TIME
        LIKE_PROBABILITY_USED = self.config.LIKE_PROBABILITY
        VISIT_PROFILE_PROBABILITY_USED = self.config.VISIT_ENABLE
        PROFILE_FOLLOW_PROBABILITY_USED = self.config.PROFILE_FOLLOW_PROBABILITY
        MIN_FOLLOWS_PER_VIDEO_USED = self.config.MIN_FOLLOWS_PER_VIDEO
        MAX_FOLLOWS_PER_VIDEO_USED = self.config.MAX_FOLLOWS_PER_VIDEO
        MIN_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MIN
        MAX_LIKES_PER_VIDEO_USED = self.config.COMMENT_LIKE_COUNT_MAX

        import concurrent.futures

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=MAX_WORKERS_USED
            ) as executor:
                futures = []
                for i in range(MAX_WORKERS_USED):
                    browser_id = self.config.BIT_BROWSER_IDS[
                        i % len(self.config.BIT_BROWSER_IDS)
                    ]
                    reporter = DataReporter(
                        device_code=self.config.DEVICE_CODE,
                        browser_id=browser_id,
                        send_ws_message_func=self._send_ws_message_for_reporter,
                    )
                    self.data_reporters[browser_id] = reporter
                    self._send_ws_message(
                        {
                            "browserId": browser_id,
                            "cmd": "RunStateReq",
                            "id": self.config.DEVICE_CODE,
                            "state": "running" if len(browser_id) == 32 else "error",
                        }
                    )
                    time.sleep(0.2)
                    future = executor.submit(
                        self.search_keywords_loop,
                        browser_id,
                        WAIT_TIME_USED,
                        LIKE_PROBABILITY_USED,
                        VISIT_PROFILE_PROBABILITY_USED,
                        PROFILE_FOLLOW_PROBABILITY_USED,
                        MIN_FOLLOWS_PER_VIDEO_USED,
                        MAX_FOLLOWS_PER_VIDEO_USED,
                        MIN_LIKES_PER_VIDEO_USED,
                        MAX_LIKES_PER_VIDEO_USED,
                        i + 1,
                        reporter,
                        MAX_WORKERS_USED,
                        i + 1,
                    )
                    futures.append(future)
                    if i < MAX_WORKERS_USED - 1:
                        time.sleep(2.5)

                while futures:
                    done, not_done = concurrent.futures.wait(futures, timeout=1)
                    for future in done:
                        try:
                            future.result()
                        except Exception as e:
                            log.error(f"线程执行出错: {e}")
                    futures = list(not_done)
                    if self._check_stop_signal():
                        self.utils._stop_flag.set()
                        for future in futures:
                            future.cancel()
                        break
        except Exception as e:
            log.error(f"并发执行异常: {e}")
            raise

    def _open_first_video_for_keyword(
        self, driver, word: str, wait_time: int, browser_number: int | None = None
    ) -> bool:
        self.utils.check_stop_signal()
        wait = WebDriverWait(driver, wait_time)
        search_input = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-e2e="searchbar-input"]')
            )
        )
        DouyinBrowserActions.clear_input(search_input)
        search_input.send_keys(word)
        driver.find_element(By.CSS_SELECTOR, '[data-e2e="searchbar-button"]').click()
        try:
            wait.until(
                EC.presence_of_element_located((By.ID, "waterFallScrollContainer"))
            )
        except Exception:
            pass
        self.utils.safe_sleep(1, browser_number=browser_number)
        try:
            card = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//div[@id='waterFallScrollContainer']//div[contains(@class, 'videoImage')]",
                    )
                )
            )
            driver.execute_script("arguments[0].click();", card)
            self.utils.debug_log("info", "已点击瀑布流首个视频卡片", browser_number)
        except Exception:
            try:
                card2 = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.CSS_SELECTOR,
                            '[data-e2e="scroll-list"] > li div[id="sliderVideo"]',
                        )
                    )
                )
                driver.execute_script("arguments[0].click();", card2)
                self.utils.debug_log(
                    "info", "已点击滚动列表首个视频卡片", browser_number
                )
            except Exception:
                self.utils.debug_log(
                    "warning", "未找到可点击的视频卡片", browser_number
                )
                return False
        self.utils.safe_sleep(4, browser_number=browser_number)
        try:
            driver.find_element(
                By.CSS_SELECTOR,
                '[data-e2e="recommend-guide-mask"] .semi-button-content',
            ).click()
        except Exception:
            pass
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        '.modal-video-container [data-e2e="feed-active-video"]',
                    )
                )
            )
            self.utils.debug_log("info", "检测到搜索弹层已打开", browser_number)
        except Exception:
            pass
        return True

    def search_keywords_loop(
        self,
        browser_id: str,
        wait_time: int,
        like_probability: int,
        visit_profile_probability: int,
        profile_follow_probability: int,
        min_follows_per_video: int,
        max_follows_per_video: int,
        min_likes_per_video: int,
        max_likes_per_video: int,
        browser_number: int | None = None,
        reporter: DataReporter | None = None,
        browser_count: int | None = None,
        browser_index: int | None = None,
    ):
        cfg = get_config()
        sent_completion_report = False
        if reporter:
            with self._kw_lock:
                reporter.set_total_links(len(self.keyword_queue))
        self.utils.safe_check_license()
        driver = None
        try:
            driver = self.utils.get_driver(browser_id, browser_number)
            if driver is None:
                raise Exception("浏览器创建失败，无法继续执行")
            driver.get("https://www.douyin.com")
            self.utils.safe_sleep(4, browser_number=browser_number)
            with self._kw_lock:
                if not self.keyword_queue:
                    rebuilt = DouyinConfigParser.parse_keywords(cfg.KEYWORDS or [])
                    added = 0
                    for kw in rebuilt:
                        if (
                            kw not in self.keyword_processed
                            and kw not in self.keyword_queue
                        ):
                            self.keyword_queue.append(kw)
                            added += 1
                    if reporter:
                        reporter.set_total_links(len(self.keyword_queue))
                    log.info(
                        f"队列为空，重新构建并加入 {added} 项，当前队列 {len(self.keyword_queue)} 项"
                    )
            idx = 0
            empty_retries = 0
            while not self.utils._stop_flag.is_set():
                with self._kw_lock:
                    if self.keyword_queue:
                        word = self.keyword_queue.popleft()
                    else:
                        word = None
                if not word:
                    empty_retries += 1
                    self.utils.safe_sleep(3, browser_number=browser_number)
                    if empty_retries >= 5:
                        if reporter:
                            reporter.set_completed(True)
                            sent_completion_report = True
                        break
                    continue
                if self.utils._stop_flag.is_set():
                    if reporter:
                        reporter.set_completed(True)
                        sent_completion_report = True
                    break
                try:
                    empty_retries = 0
                    ok = self._open_first_video_for_keyword(
                        driver, word, wait_time, browser_number
                    )
                    if not ok:
                        if reporter:
                            reporter.set_keywords(word)
                        continue
                    url = driver.current_url
                    like_probability_val = like_probability / 100.0
                    visit_profile_probability_val = visit_profile_probability / 100.0
                    profile_follow_probability_val = profile_follow_probability / 100.0
                    comment_reply_probability_val = (
                        cfg.COMMENT_REPLY_PROBABILITY / 100.0
                    )
                    if reporter:
                        reporter.set_keywords(word)
                    target_videos = random.randint(*cfg.MAX_SCROLL_VIDEO)
                    processed_videos = 0
                    while (
                        processed_videos < target_videos
                        and not self.utils._stop_flag.is_set()
                    ):
                        try:
                            try:
                                active = driver.find_element(
                                    By.CSS_SELECTOR,
                                    '.modal-video-container [data-e2e="feed-active-video"]',
                                )
                            except Exception:
                                active = driver.find_element(
                                    By.CSS_SELECTOR,
                                    ".modal-video-container .liveSearchPlayer",
                                )
                                self.utils.safe_sleep(
                                    random.uniform(10, 30),
                                    browser_number=browser_number,
                                )
                                try:
                                    body = driver.find_element(By.TAG_NAME, "body")
                                    DouyinBrowserActions.scroll_element_sync(
                                        driver, body, delta_y=400, sleep_time=2
                                    )
                                except Exception:
                                    pass
                                continue
                            try:
                                active.find_element(
                                    By.CLASS_NAME, "playerContainer"
                                ).click()
                            except Exception:
                                pass
                            try:
                                active.find_element(
                                    By.CLASS_NAME, "comment-mainContent"
                                )
                            except Exception:
                                try:
                                    btn = active.find_element(
                                        By.CSS_SELECTOR,
                                        '[data-e2e="feed-comment-icon"]',
                                    )
                                    btn.click()
                                    self.utils.safe_sleep(
                                        3, browser_number=browser_number
                                    )
                                except Exception:
                                    pass
                            if (
                                cfg.ENABLE_VIDEO_COMMENT
                                and random.randint(1, 100) <= cfg.VIDEO_REPLY_RATE
                            ):
                                video_comments = (
                                    DouyinConfigParser.parse_video_comments(
                                        getattr(cfg, "VIDEO_COMMENTS", "") or ""
                                    )
                                )
                                if video_comments:
                                    comment_text = random.choice(video_comments)
                                    try:
                                        DouyinCommentActions.leave_video_comment_async(
                                            driver,
                                            comment_text,
                                            active_element=active,
                                            ws_push_func=None,
                                            sleep=self.utils.safe_sleep,
                                        )
                                        if reporter:
                                            reporter.set_action("videoComment")
                                            reporter.increment_video_comment(1)
                                    except Exception:
                                        pass
                            self._process_comments(
                                active, driver, cfg, reporter, browser_number
                            )
                            processed_videos += 1
                            try:
                                if reporter:
                                    reporter.set_action("video")
                                    reporter.increment_video(1)
                            except Exception:
                                pass
                            try:
                                body = driver.find_element(By.TAG_NAME, "body")
                                DouyinBrowserActions.scroll_element_sync(
                                    driver, body, delta_y=600, sleep_time=2
                                )
                            except Exception:
                                pass
                            self.utils.safe_sleep(
                                random.uniform(1, 2), browser_number=browser_number
                            )
                        except Exception:
                            self.utils.safe_sleep(1, browser_number=browser_number)
                    with self._kw_lock:
                        self.keyword_processed.add(word)
                    if reporter:
                        reporter.increment_keywords_ok(1)
                    try:
                        driver.find_element(By.CLASS_NAME, "uRH5Oxnw").click()
                    except Exception:
                        pass
                    self.utils.safe_sleep(
                        random.uniform(5, 10), browser_number=browser_number
                    )
                    driver.get("https://www.douyin.com")
                    self.utils.safe_sleep(3, browser_number=browser_number)
                    idx += 1
                except Exception as e:
                    if self.utils._stop_flag.is_set():
                        raise KeyboardInterrupt("收到全局停止信号")
                    log.error(f"处理关键词异常: {e}")
                    self.utils.safe_sleep(3, browser_number=browser_number)
                    try:
                        driver.get("https://www.douyin.com")
                        self.utils.safe_sleep(2, browser_number=browser_number)
                    except Exception:
                        pass
            if reporter and self.utils._stop_flag.is_set():
                reporter.set_completed(True)
                sent_completion_report = True
        except KeyboardInterrupt:
            pass
        except Exception as e:
            log.error(f"程序异常退出: {e}")
        finally:
            if reporter and not sent_completion_report:
                reporter.force_report()
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _process_comments(self, active, driver, cfg, reporter, browser_number):
        start_index = 0
        follow_index = 0
        like_index = 0
        threshold_enabled = getattr(cfg, "COMMENT_THRESHOLD_ENABLE", False)
        max_follow = random.randint(
            cfg.MIN_FOLLOWS_PER_VIDEO, cfg.MAX_FOLLOWS_PER_VIDEO
        )
        max_like = random.randint(
            cfg.COMMENT_LIKE_COUNT_MIN, cfg.COMMENT_LIKE_COUNT_MAX
        )
        scroll_times = random.randint(*cfg.MAX_COMMENT)
        for _ in range(scroll_times):
            try:
                comment_list = active.find_elements(
                    By.CSS_SELECTOR, '[data-e2e="comment-list"] > div'
                )
            except Exception:
                break
            if len(comment_list) <= 1:
                break
            new_list = comment_list[start_index:-1]
            start_index = len(comment_list) - 1
            for comment in new_list:
                time_matched = False
                if threshold_enabled:
                    try:
                        dt = parse_comment_dt(comment)
                        if within_threshold(dt):
                            time_matched = True
                        else:
                            continue
                    except Exception:
                        continue
                comment_ok = False
                try:
                    if (
                        cfg.ENABLE_COMMENT_TEMPLATES
                        and cfg.ENABLE_SEARCH_KEYWORDS
                        and comment.text
                    ):
                        keywords = DouyinConfigParser.parse_keywords(
                            cfg.COMMENT_FILTER_KEYWORDS or []
                        )
                        norm_comment = DouyinConfigParser.normalize_text(comment.text)
                        for kw in keywords:
                            if DouyinConfigParser.normalize_text(kw) in norm_comment:
                                comment_ok = True
                                break
                except Exception:
                    pass
                if threshold_enabled and time_matched:
                    should_like = cfg.ENABLE_LIKE and like_index < max_like
                else:
                    should_like = cfg.ENABLE_LIKE and (
                        comment_ok
                        or (
                            like_index < max_like
                            and random.randint(1, 100) <= cfg.LIKE_PROBABILITY
                        )
                    )
                if should_like:
                    try:
                        like_button = comment.find_element(
                            By.XPATH,
                            ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
                        )
                        like_button.click()
                        like_index += 1
                        if reporter:
                            reporter.set_action("like")
                            reporter.increment_like(1)
                        self.utils.safe_sleep(
                            random.randint(cfg.LIKE_WAIT_MIN, cfg.LIKE_WAIT_MAX),
                            browser_number=browser_number,
                        )
                    except Exception:
                        pass
                if threshold_enabled and time_matched:
                    should_visit = cfg.ENABLE_PROFILE_VISIT and cfg.ENABLE_FOLLOW
                else:
                    should_visit = cfg.ENABLE_PROFILE_VISIT and (
                        comment_ok or random.randint(1, 100) <= cfg.VISIT_ENABLE
                    )
                if should_visit:
                    try:
                        avatar_link = comment.find_element(
                            By.CSS_SELECTOR, ".comment-item-avatar a"
                        )
                        try:
                            DouyinBrowserActions.ensure_element_centered(
                                driver, avatar_link, sleep=self.utils.safe_sleep
                            )
                        except Exception:
                            pass
                        avatar_link.click()
                        self.utils.safe_sleep(
                            random.randint(3, 5), browser_number=browser_number
                        )
                        driver.switch_to.window(driver.window_handles[1])
                        self.utils.safe_sleep(
                            random.randint(7, 15), browser_number=browser_number
                        )
                        force_follow = comment_ok
                        follow_prob = (
                            100 if force_follow else cfg.PROFILE_FOLLOW_PROBABILITY
                        )
                        if (
                            cfg.ENABLE_FOLLOW
                            and follow_index < max_follow
                            and (force_follow or random.randint(1, 100) <= follow_prob)
                        ):
                            try:
                                follow_button = driver.find_element(
                                    By.CSS_SELECTOR, '[data-e2e="user-info-follow-btn"]'
                                )
                                try:
                                    button_text = follow_button.text.strip()
                                    if "已关注" not in button_text:
                                        follow_button.click()
                                        follow_index += 1
                                        if reporter:
                                            reporter.set_action("follow")
                                            reporter.increment_follow(1)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        try:
                            if getattr(cfg, "ENABLE_DM", True):
                                dm_list = DouyinConfigParser.parse_dm_messages(
                                    getattr(cfg, "DM_MESSAGES", "") or ""
                                )
                                if dm_list:
                                    dm_prob = float(getattr(cfg, "DM_PROBABILITY", 0))
                                    force_dm = threshold_enabled and time_matched
                                    if force_dm or random.randint(1, 100) <= dm_prob:
                                        dm_text = random.choice(dm_list)
                                        ok = self.utils.send_direct_message(
                                            driver,
                                            dm_text,
                                            getattr(cfg, "DM_WAIT_MIN", 5),
                                            getattr(cfg, "DM_WAIT_MAX", 12),
                                            browser_number,
                                        )
                                        if ok and reporter:
                                            reporter.set_action("letter")
                                            reporter.increment_letter(1)
                                else:
                                    self.utils.debug_log(
                                        "warning",
                                        "DM_MESSAGES 列表为空，跳过私信",
                                        browser_number,
                                    )
                        except Exception:
                            pass
                        self.utils.safe_sleep(
                            random.randint(cfg.VISIT_MIN, cfg.VISIT_MAX),
                            browser_number=browser_number,
                        )
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                        self.utils.safe_sleep(
                            random.randint(3, 8), browser_number=browser_number
                        )
                    except Exception:
                        try:
                            driver.switch_to.window(driver.window_handles[0])
                        except Exception:
                            pass
                if cfg.ENABLE_COMMENT_REPLY:
                    try:
                        comment_replies = DouyinConfigParser.parse_comment_replies(
                            getattr(cfg, "COMMENT_REPLIES", "") or ""
                        )
                        if threshold_enabled and time_matched:
                            should_reply = bool(comment_replies)
                        else:
                            should_reply = comment_replies and (
                                comment_ok
                                or random.randint(1, 100)
                                <= cfg.COMMENT_REPLY_PROBABILITY
                            )
                        if should_reply:
                            wait_time = random.randint(
                                cfg.COMMENT_WAIT_MIN, cfg.COMMENT_WAIT_MAX
                            )
                            self.utils.safe_sleep(
                                wait_time, browser_number=browser_number
                            )
                            reply_content = random.choice(comment_replies)
                            try:
                                DouyinCommentActions.reply_to_comment_async(
                                    driver,
                                    comment,
                                    reply_content,
                                    active_element=active,
                                    ws_push_func=None,
                                    sleep=self.utils.safe_sleep,
                                )
                                if reporter:
                                    reporter.set_action("comment")
                                    reporter.increment_comment(1)
                            except Exception:
                                pass
                    except Exception:
                        pass
            try:
                padding = active.find_element(
                    By.CSS_SELECTOR, '[data-e2e="comment-list"] > div:last-child'
                ).text
                if padding == "暂时没有更多评论":
                    break
            except Exception:
                pass
            try:
                ActionChains(driver).scroll_from_origin(
                    ScrollOrigin.from_element(
                        active.find_element(By.CLASS_NAME, "comment-mainContent")
                    ),
                    0,
                    600,
                ).perform()
                self.utils.safe_sleep(
                    random.randint(4, 8), browser_number=browser_number
                )
            except Exception:
                break
