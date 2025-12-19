from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin
from selenium.webdriver.chrome.service import Service

from asyncio import sleep
from random import randint, choice
from datetime import datetime
import sys

from ..tools import log, config
from ..tools.ws_client import WSClient
from ..tools.core import AbstractCrawler, openBrowser
from ..tools.license import LicenseManager, LicenseException
from ..tools.douyin_common import (
    DouyinConfigParser,
    DouyinCommentActions,
    DouyinBrowserActions,
)


class DouyinCrawler(AbstractCrawler):
    driver: WebDriver

    def __init__(self, ws):
        self.ws: WSClient = ws
        self.word = None  # 初始化 word 属性
        self.license_manager = LicenseManager()  # 卡密管理器
        self._license_invalid = False  # 卡密失效标志

    def _parse_keywords(self):
        """解析关键字配置"""
        raw = self.ws.config.COMMENT_FILTER_KEYWORDS or []
        return DouyinConfigParser.parse_keywords(raw)

    def _normalize_text(self, t):
        """文本标准化（转小写、去除多余空格）"""
        return DouyinConfigParser.normalize_text(t)

    def _parse_video_comments(self):
        """解析视频留言内容列表，使用 -&- 作为分隔符"""
        raw = getattr(self.ws.config, 'VIDEO_COMMENTS', '') or ''
        return DouyinConfigParser.parse_video_comments(raw)

    def _parse_comment_replies(self):
        """解析评论回复内容列表，使用 -&- 作为分隔符"""
        raw = getattr(self.ws.config, 'COMMENT_REPLIES', '') or ''
        return DouyinConfigParser.parse_comment_replies(raw)

    async def scroll(self, dom: WebElement):
        await DouyinBrowserActions.scroll_element_async(self.driver, dom, delta_y=200, sleep_time=2)

    def clear(self, dom: WebElement):
        DouyinBrowserActions.clear_input(dom)

    async def search(self):
        driver = self.driver
        await sleep(2)
        while True:
            if self.ws.config.KEYWORDS:
                self.word = word = self.ws.config.KEYWORDS.pop(0)
            else:
                break
            # searchBox = driver.find_element(By.CLASS_NAME, "YEhxqQNi")
            searchBox = driver.find_element(
                By.CSS_SELECTOR, '[data-e2e="searchbar-input"]'
            )

            self.clear(searchBox)
            searchBox.send_keys(word)
            driver.find_element(
                By.CSS_SELECTOR, '[data-e2e="searchbar-button"]'
            ).click()
            await self.ws.push(keywords=word)
            await sleep(3)

            try:
                driver.find_element(
                    By.XPATH,
                    "//div[@id='waterFallScrollContainer']//div[contains(@class, 'videoImage')]",
                ).click()
            except NoSuchElementException:
                driver.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="scroll-list"] > li div[id="sliderVideo"]',
                ).click()
            await sleep(4)

            try:
                driver.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="recommend-guide-mask"] .semi-button-content',
                ).click()
            except NoSuchElementException:
                pass
            await self.traversal_video()

    async def traversal_video(self):
        driver = self.driver
        MAX_SCROLL_VIDEO = randint(*self.ws.config.MAX_SCROLL_VIDEO)
        for _ in range(MAX_SCROLL_VIDEO):
            try:
                active = driver.find_element(
                    By.CSS_SELECTOR,
                    '.modal-video-container [data-e2e="feed-active-video"]',
                )
            except NoSuchElementException:
                active = driver.find_element(
                    By.CSS_SELECTOR,
                    ".modal-video-container .liveSearchPlayer",
                )
                await sleep(randint(10, 30))
                await self.scroll(active)
                continue

            # pause video
            active.find_element(By.CLASS_NAME, "playerContainer").click()

            try:
                active.find_element(By.CLASS_NAME, "comment-mainContent")
            except NoSuchElementException:
                # click comment
                active.find_element(
                    By.CSS_SELECTOR, '[data-e2e="feed-comment-icon"]'
                ).click()
                await sleep(3)

            # 视频留言功能
            if self.ws.config.ENABLE_VIDEO_COMMENT:
                video_comments = self._parse_video_comments()
                if video_comments:
                    video_reply_probability = self.ws.config.VIDEO_REPLY_RATE / 100.0
                    if randint(1, 100) <= self.ws.config.VIDEO_REPLY_RATE:
                        comment_text = choice(video_comments)
                        log.debug(f"开始发布视频留言: {comment_text[:30]}...")
                        await self._leave_video_comment(active, comment_text)

            # self.commentNew(active)
            await self.comment(active)
            await self.scroll(active)
            await self.ws.push(video=1)

        driver.find_element(By.CLASS_NAME, "uRH5Oxnw").click()
        await sleep(2)

    async def comment(self, active):
        driver = self.driver

        startIndex = 0
        followIndex = 0
        likeIndex = 0
        maxFollow = randint(self.ws.config.MIN_FOLLOWS_PER_VIDEO, self.ws.config.MAX_FOLLOWS_PER_VIDEO)
        maxLike = randint(self.ws.config.COMMENT_LIKE_COUNT_MIN, self.ws.config.COMMENT_LIKE_COUNT_MAX)
        for _ in range(randint(*self.ws.config.MAX_COMMENT)):
            commentList = active.find_elements(
                By.CSS_SELECTOR, '[data-e2e="comment-list"] > div'
            )

            # 暂无评论
            if len(commentList) == 1:
                log.debug("暂无评论")
                break

            newList = commentList[startIndex:-1]

            newLen = len(newList)
            # maxLike = min(4, randint(0, newLen))
            # randomLike = random.sample(range(0, newLen), maxLike)

            # maxEnterHome = min(4, randint(0, newLen))
            # randomfollow = random.sample(range(0, newLen), maxEnterHome)

            log.debug(f"start loop...{startIndex} len {newLen}")
            startIndex = len(commentList) - 1
            for _, comment in enumerate(newList):
                # https://juejin.cn/post/7028451270029475847
                # comment.click()
                # await sleep(1)
                commentOk = False
                # 使用标准化的关键字匹配（需要同时启用ENABLE_COMMENT_TEMPLATES和ENABLE_SEARCH_KEYWORDS）
                if (self.ws.config.ENABLE_COMMENT_TEMPLATES 
                    and self.ws.config.ENABLE_SEARCH_KEYWORDS 
                    and comment.text):
                    keywords = self._parse_keywords()
                    norm_comment = self._normalize_text(comment.text)
                    for kw in keywords:
                        if self._normalize_text(kw) in norm_comment:
                            commentOk = True
                            break

                # 点赞逻辑：关键词命中后直接执行，否则按概率执行
                if self.ws.config.ENABLE_LIKE and (
                    commentOk
                    or (
                        likeIndex < maxLike
                        and randint(1, 100) <= self.ws.config.LIKE_PROBABILITY
                    )
                ):
                    log.debug(f"点赞-> {comment.text}")
                    try:
                        like_button = comment.find_element(
                            By.XPATH,
                            ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]"
                        )
                        await sleep(0.5)
                        like_button.click()
                    except ElementClickInterceptedException:
                        driver.execute_script(
                            "arguments[0].click();",
                            comment.find_element(
                                By.XPATH,
                                ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
                            ),
                        )
                    likeIndex += 1
                    await self.ws.push(like=1)
                    await sleep(randint(self.ws.config.LIKE_WAIT_MIN, self.ws.config.LIKE_WAIT_MAX))

                # 关注/主页逻辑：关键词命中后直接执行，否则按概率执行
                should_visit = self.ws.config.ENABLE_PROFILE_VISIT and (
                    commentOk or randint(1, 100) <= self.ws.config.VISIT_ENABLE
                )
                if should_visit:
                    log.debug(f"进入主页-> {comment.text}")
                    try:
                        avatar_link = comment.find_element(
                            By.CSS_SELECTOR, ".comment-item-avatar a"
                        )
                        await sleep(0.5)
                        avatar_link.click()
                    except ElementClickInterceptedException:
                        driver.execute_script(
                            "arguments[0].click();",
                            comment.find_element(
                                By.CSS_SELECTOR, ".comment-item-avatar a"
                            ),
                        )
                    except NoSuchElementException:
                        # dom还没加载完成,点击上层使窗口滚动到dom显示,使其加载子元素
                        comment.find_element(
                            By.CSS_SELECTOR, ".comment-item-avatar"
                        ).click()
                        await sleep(2)

                        comment.find_element(
                            By.CSS_SELECTOR, ".comment-item-avatar a"
                        ).click()

                    await sleep(randint(3, 5))
                    driver.switch_to.window(driver.window_handles[1])
                    await sleep(randint(7, 15))

                    # 如果关键词匹配，强制关注（不受 profile_follow_probability 影响）
                    force_follow = commentOk
                    follow_prob = 100 if force_follow else self.ws.config.PROFILE_FOLLOW_PROBABILITY
                    if (
                        self.ws.config.ENABLE_FOLLOW
                        and followIndex < maxFollow
                        and (force_follow or randint(1, 100) <= follow_prob)
                    ):
                        try:
                            follow_button = driver.find_element(
                                By.CSS_SELECTOR, '[data-e2e="user-info-follow-btn"]'
                            )

                            # 检查关注按钮状态，避免重复关注
                            try:
                                button_text = follow_button.text.strip()
                                if "已关注" in button_text:
                                    log.debug("用户已被关注，跳过关注操作")
                                else:
                                    follow_button.click()
                                    followIndex += 1
                                    await self.ws.push(follow=1)
                            except Exception:
                                # 无法获取按钮文本，输出该用户不存在
                                log.debug("该用户不存在")

                        except ElementClickInterceptedException:
                            # 处理点击被拦截的情况
                            timestamp = datetime.now().strftime(
                                "%Y年%m月%d日_%H时%M分%S秒"
                            )
                            driver.get_screenshot_as_file(f"screenshot_{timestamp}.png")

                            try:
                                follow_button = driver.find_element(
                                    By.CSS_SELECTOR, '[data-e2e="user-info-follow-btn"]'
                                )

                                # 再次检查关注按钮状态
                                try:
                                    button_text = follow_button.text.strip()
                                    if "已关注" in button_text:
                                        log.debug("用户已被关注，跳过关注操作")
                                    else:
                                        driver.execute_script("arguments[0].click();", follow_button)
                                        log.debug("💗关注用户成功")
                                        followIndex += 1
                                        await self.ws.push(follow=1)
                                except Exception:
                                    # 无法获取按钮文本，输出该用户不存在
                                    log.debug("该用户不存在")

                            except Exception:
                                # 按钮不存在或其他异常，输出该用户不存在
                                log.debug("该用户不存在")

                        except NoSuchElementException:
                            # 按钮不存在，输出该用户不存在
                            log.debug("该用户不存在")

                        await sleep(randint(self.ws.config.VISIT_MIN, self.ws.config.VISIT_MAX))
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])

                    await sleep(randint(3, 8))

                # 评论回复逻辑：关键词命中后直接执行，否则按概率执行
                if self.ws.config.ENABLE_COMMENT_REPLY:
                    comment_replies = self._parse_comment_replies()
                    should_reply = comment_replies and (
                        commentOk or randint(1, 100) <= self.ws.config.COMMENT_REPLY_PROBABILITY
                    )
                    if should_reply:
                        try:
                            # 等待一段时间再回复
                            wait_time = randint(
                                self.ws.config.COMMENT_WAIT_MIN,
                                self.ws.config.COMMENT_WAIT_MAX
                            )
                            await sleep(wait_time)
                            # 从回复内容列表中随机选择一条回复
                            reply_content = choice(comment_replies)
                            # 执行回复
                            await self._reply_to_comment(active, comment, reply_content)
                        except Exception as e:
                            log.debug(f"回复评论过程中出错: {e}")

            padding = active.find_element(
                By.CSS_SELECTOR, '[data-e2e="comment-list"] > div:last-child'
            ).text
            if padding == "暂时没有更多评论":
                break

            ActionChains(self.driver).scroll_from_origin(
                ScrollOrigin.from_element(
                    active.find_element(By.CLASS_NAME, "comment-mainContent")
                ),
                0,
                600,
            ).perform()
            await sleep(randint(4, 8))

    async def _leave_video_comment(self, active, comment_text):
        """在当前视频页面留下评论"""
        return await DouyinCommentActions.leave_video_comment_async(
            self.driver,
            comment_text,
            active_element=active,
            ws_push_func=self.ws.push
        )

    async def _reply_to_comment(self, active, comment, reply_text):
        """回复指定评论"""
        return await DouyinCommentActions.reply_to_comment_async(
            self.driver,
            comment,
            reply_text,
            active_element=active,
            ws_push_func=self.ws.push
        )

    def _on_license_invalid(self):
        """当卡密失效时的回调函数（异步环境）"""
        log.error("=" * 50)
        log.error("卡密已失效，正在停止程序...")
        log.error("=" * 50)
        # 设置标志，在异步执行中检查
        self._license_invalid = True

    async def start(self):
        try:
            # 等待配置初始化完成
            await self.ws.ready_event.wait()
            
            # 从 ws.config 更新 LicenseManager 的参数（配置从服务器接收后）
            # SIBERIAN_URL 和 SIBERIAN_KEY 从服务器接收的配置中获取
            if hasattr(self.ws.config, 'SIBERIAN_URL') and self.ws.config.SIBERIAN_URL:
                self.license_manager.url = self.ws.config.SIBERIAN_URL
            if hasattr(self.ws.config, 'SIBERIAN_KEY') and self.ws.config.SIBERIAN_KEY:
                self.license_manager.key = self.ws.config.SIBERIAN_KEY
            
            # DEVICE_CODE、UUID 和 ACTIVE_URL 从全局 config 读取（通常通过环境变量或初始配置）
            from ..tools.config import get_config
            global_config = get_config()
            if hasattr(global_config, 'DEVICE_CODE') and global_config.DEVICE_CODE:
                self.license_manager.code = global_config.DEVICE_CODE
            if hasattr(global_config, 'UUID') and global_config.UUID:
                self.license_manager.uuid = global_config.UUID
            if hasattr(global_config, 'ACTIVE_URL') and global_config.ACTIVE_URL:
                self.license_manager.active_url = global_config.ACTIVE_URL
            
            # 验证卡密（带UUID）
            if not self.license_manager.verify_license():
                raise LicenseException("❌ 卡密验证失败！")
            
            # 设置停止回调
            self.license_manager.set_stop_callback(self._on_license_invalid)
            
            # 启动定期检查（延迟一点，确保配置已更新）
            await sleep(0.5)
            self.license_manager.start_periodic_check()
            
            # 检查卡密失效标志
            if self._license_invalid:
                raise LicenseException("卡密已失效，程序已停止")
            
            if not len(self.ws.config.BIT_BROWSER_IDS):
                raise Exception("请至少传一个比特浏览器id")

            res = openBrowser(self.ws.config.BIT_BROWSER_IDS[0])
            log.debug(res)

            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_experimental_option(
                "debuggerAddress", res["data"]["http"]
            )

            self.driver = driver = webdriver.Chrome(
                service=Service(res["data"]["driver"]), options=chrome_options
            )
            driver.implicitly_wait(6)

            # 除第1个tab之外的标签关闭
            for tab in driver.window_handles[1:]:
                driver.switch_to.window(tab)
                driver.close()
            driver.switch_to.window(driver.window_handles[0])
            await sleep(1)

            driver.get("https://www.douyin.com")

            await sleep(4)
            try:
                # 在执行前检查卡密失效标志
                if self._license_invalid:
                    raise LicenseException("卡密已失效，程序已停止")
                
                await self.search()
                
                # 在执行后再次检查
                if self._license_invalid:
                    raise LicenseException("卡密已失效，程序已停止")
                
                await self.ws.push(isCompleted=True)
            finally:
                timestamp = datetime.now().strftime("%Y年%m月%d日_%H时%M分%S秒")
                driver.get_screenshot_as_file(f"screenshot_{timestamp}.png")
        except LicenseException:
            # 卡密失效异常，直接抛出
            log.error("程序因卡密失效而停止")
            raise
        except Exception as e:
            log.debug(
                f"发生异常:{e}，当前关键字：{self.word}",
                exc_info=True,
            )
            raise
        finally:
            # 停止卡密定期检查
            self.license_manager.stop_periodic_check()
