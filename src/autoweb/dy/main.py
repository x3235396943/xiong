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
import json
import re

from ..tools import log, config
from ..tools.web_client import WSClient
from ..tools.base import AbstractCrawler
from ..tools.bit_api import openBrowser


class DouyinCrawler(AbstractCrawler):
    driver: WebDriver

    def __init__(self, ws):
        self.ws: WSClient = ws
        self.word = None  # 初始化 word 属性

    def _parse_keywords(self):
        """解析关键字配置"""
        raw = self.ws.config.COMMENT_FILTER_KEYWORDS or []
        seps = [",", "，", " ", "\t", ";", "；"]
        kws = []
        if isinstance(raw, str):
            s = raw.strip()
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    raw = data
                else:
                    raw = [s]
            except Exception:
                raw = [s]
        if isinstance(raw, list):
            if len(raw) == 1 and isinstance(raw[0], str):
                base = raw[0]
                for sep in seps:
                    base = base.replace(sep, ",")
                kws = [x.strip() for x in base.split(",") if x.strip()]
            else:
                kws = [str(x).strip() for x in raw if str(x).strip()]
        return kws

    def _normalize_text(self, t):
        """文本标准化（转小写、去除多余空格）"""
        try:
            s = str(t).lower()
            s = re.sub(r"\s+", " ", s).strip()
            return s
        except Exception:
            return str(t)

    def _parse_video_comments(self):
        """解析视频留言内容列表，使用 -&- 作为分隔符"""
        raw = getattr(self.ws.config, 'VIDEO_COMMENTS', '') or ''
        if not raw:
            return []
        comments = []
        if isinstance(raw, str):
            s = raw.strip()
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    comments = [str(x).strip() for x in data if str(x).strip()]
                else:
                    comments = [s] if s else []
            except Exception:
                # 不是JSON，按 -&- 分隔符分割
                comments = [x.strip() for x in s.split("-&-") if x.strip()]
        elif isinstance(raw, list):
            comments = [str(x).strip() for x in raw if str(x).strip()]
        return comments if comments else []

    def _parse_comment_replies(self):
        """解析评论回复内容列表，使用 -&- 作为分隔符"""
        raw = getattr(self.ws.config, 'COMMENT_REPLIES', '') or ''
        if not raw:
            return []
        replies = []
        if isinstance(raw, str):
            s = raw.strip()
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    replies = [str(x).strip() for x in data if str(x).strip()]
                else:
                    replies = [s] if s else []
            except Exception:
                # 不是JSON，按 -&- 分隔符分割
                replies = [x.strip() for x in s.split("-&-") if x.strip()]
        elif isinstance(raw, list):
            replies = [str(x).strip() for x in raw if str(x).strip()]
        return replies if replies else []

    async def scroll(self, dom: WebElement):
        ActionChains(self.driver).scroll_from_origin(
            ScrollOrigin.from_element(dom), 0, 200
        ).perform()
        await sleep(2)

    def clear(self, dom: WebElement):
        if sys.platform == "win32":
            dom.send_keys(Keys.CONTROL, "a")
        elif sys.platform == "darwin":  # Mac
            dom.send_keys(Keys.COMMAND, "a")
        dom.send_keys(Keys.BACKSPACE)

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
                            driver.find_element(
                                By.CSS_SELECTOR, '[data-e2e="user-info-follow-btn"]'
                            ).click()
                            followIndex += 1
                            await self.ws.push(follow=1)
                        except ElementClickInterceptedException:
                            timestamp = datetime.now().strftime(
                                "%Y年%m月%d日_%H时%M分%S秒"
                            )
                            driver.get_screenshot_as_file(f"screenshot_{timestamp}.png")
                            driver.execute_script(
                                "arguments[0].click();",
                                driver.find_element(
                                    By.CSS_SELECTOR, '[data-e2e="user-info-follow-btn"]'
                                ),
                            )
                            log.debug("💗关注用户成功")
                            followIndex += 1
                            await self.ws.push(follow=1)
                        except NoSuchElementException:
                            log.debug("用户不存在")
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
        driver = self.driver
        try:
            # 查找评论输入框
            comment_input = active.find_element(
                By.CSS_SELECTOR,
                '.GXmFLge7.comment-input-inner-container'
            )
            # 点击评论输入框
            driver.execute_script("arguments[0].click();", comment_input)
            await sleep(0.5)
            # 输入评论文本
            ActionChains(driver).send_keys(comment_text).perform()
            await sleep(0.5)
            # 尝试点击发送按钮
            try:
                send_button = active.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="comment-post"]'
                )
                driver.execute_script("arguments[0].click();", send_button)
                log.debug(f"成功发布视频评论: {comment_text[:20]}...")
                await sleep(1)
                await self.ws.push(videoComment=1)
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                log.debug(f"通过回车键发送视频评论: {comment_text[:20]}...")
                await sleep(1)
                await self.ws.push(videoComment=1)
                return True
        except Exception as e:
            log.debug(f"发布视频评论失败: {e}")
            return False

    async def _reply_to_comment(self, active, comment, reply_text):
        """回复指定评论"""
        driver = self.driver
        try:
            # 查找评论的回复按钮
            reply_button = comment.find_element(
                By.CSS_SELECTOR,
                'div:nth-child(2) > div > div:nth-child(4) > div > div:nth-child(3) > div'
            )
            # 点击回复按钮
            driver.execute_script("arguments[0].click();", reply_button)
            await sleep(0.5)
            # 输入回复文本
            ActionChains(driver).send_keys(reply_text).perform()
            await sleep(0.5)
            # 尝试点击发送按钮
            try:
                send_button = active.find_element(
                    By.CSS_SELECTOR,
                    '[data-e2e="comment-post"]'
                )
                driver.execute_script("arguments[0].click();", send_button)
                log.debug(f"成功回复评论: {reply_text[:20]}...")
                await sleep(1)
                await self.ws.push(comment=1)
                return True
            except:
                # 如果找不到发送按钮，尝试按回车键
                ActionChains(driver).send_keys(Keys.RETURN).perform()
                log.debug(f"通过回车键发送回复: {reply_text[:20]}...")
                await sleep(1)
                await self.ws.push(comment=1)
                return True
        except Exception as e:
            log.debug(f"回复评论失败: {e}")
            return False

    async def start(self):
        try:
            # 等待配置初始化完成
            await self.ws.ready_event.wait()
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
                await self.search()
                await self.ws.push(isCompleted=True)
            finally:
                timestamp = datetime.now().strftime("%Y年%m月%d日_%H时%M分%S秒")
                driver.get_screenshot_as_file(f"screenshot_{timestamp}.png")
        except Exception as e:
            log.debug(
                f"发生异常:{e}，当前关键字：{self.word}",
                exc_info=True,
            )
            raise
