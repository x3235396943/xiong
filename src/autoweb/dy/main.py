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
from random import randint
from datetime import datetime
import sys

from ..tools import log, config
from ..tools.web_client import WSClient
from ..tools.base import AbstractCrawler
from ..tools.bit_api import openBrowser


class DouyinCrawler(AbstractCrawler):
    driver: WebDriver

    def __init__(self, ws):
        self.ws: WSClient = ws

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
            if config.KEYWORDS:
                self.word = word = config.KEYWORDS.pop(0)
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
            await self.ws.push({"keywords": word})
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
                driver.find_element(By.CLASS_NAME, "semi-button-content").click()
                await sleep(2)
            except NoSuchElementException:
                pass
            await self.traversal_video()

    async def traversal_video(self):
        driver = self.driver
        MAX_SCROLL_VIDEO = randint(*config.MAX_SCROLL_VIDEO)
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
            # self.commentNew(active)
            await self.comment(active)
            await self.scroll(active)
            await self.ws.push({"video": 1})

        driver.find_element(By.CLASS_NAME, "uRH5Oxnw").click()
        await sleep(2)

    async def comment(self, active):
        driver = self.driver

        startIndex = 0
        followIndex = 0
        likeIndex = 0
        maxFollow = randint(config.MIN_FOLLOWS_PER_VIDEO, config.MAX_FOLLOWS_PER_VIDEO)
        maxLike = randint(config.COMMENT_LIKE_COUNT_MIN, config.COMMENT_LIKE_COUNT_MAX)
        for _ in range(randint(*config.MAX_COMMENT)):
            commentList = active.find_elements(
                By.CSS_SELECTOR, '[data-e2e="comment-list"] > div'
            )

            # 暂无评论
            if len(commentList) == 1:
                print("暂无评论")
                break

            newList = commentList[startIndex:-1]

            newLen = len(newList)
            # maxLike = min(4, randint(0, newLen))
            # randomLike = random.sample(range(0, newLen), maxLike)

            # maxEnterHome = min(4, randint(0, newLen))
            # randomfollow = random.sample(range(0, newLen), maxEnterHome)

            print(f"start loop...{startIndex} len {newLen}")
            startIndex = len(commentList) - 1
            for _, comment in enumerate(newList):
                # https://juejin.cn/post/7028451270029475847
                # comment.click()
                # await sleep(1)
                commentOk = False
                if config.ENABLE_SEARCH_KEYWORDS and comment.text:
                    for li in config.COMMENT_FILTER_KEYWORDS:
                        if li in comment.text:
                            commentOk = True
                            break
                if config.ENABLE_LIKE and (
                    commentOk
                    or (
                        likeIndex < maxLike
                        and randint(1, 100) <= config.LIKE_PROBABILITY
                    )
                ):
                    print("点赞->", comment.text)
                    try:
                        comment.find_element(
                            By.XPATH,
                            ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
                        ).click()
                    except ElementClickInterceptedException:
                        driver.execute_script(
                            "arguments[0].click();",
                            comment.find_element(
                                By.XPATH,
                                ".//div[contains(@class, 'comment-item-stats-container')]/div[1]/p[1]",
                            ),
                        )
                    likeIndex += 1
                    await self.ws.push({"like": 1})
                    await sleep(randint(config.LIKE_WAIT_MIN, config.LIKE_WAIT_MAX))

                if (
                    config.ENABLE_PROFILE_VISIT
                    and randint(1, 100) <= config.VISIT_ENABLE
                ):
                    print("进入主页->", comment.text)
                    try:
                        comment.find_element(
                            By.CSS_SELECTOR, ".comment-item-avatar a"
                        ).click()
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

                    if (
                        config.ENABLE_FOLLOW
                        and followIndex < maxFollow
                        and randint(1, 100) <= config.PROFILE_FOLLOW_PROBABILITY
                    ):
                        try:
                            driver.find_element(
                                By.CSS_SELECTOR, '[data-e2e="user-info-follow-btn"]'
                            ).click()
                            followIndex += 1
                            await self.ws.push({"follow": 1})
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
                            print("💗关注用户成功")
                            followIndex += 1
                            await self.ws.push({"follow": 1})
                        except NoSuchElementException:
                            print("用户不存在")
                        await sleep(randint(config.VISIT_MIN, config.VISIT_MAX))
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])

                    await sleep(randint(3, 8))

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

    async def start(self):
        try:
            if not len(config.BIT_BROWSER_IDS):
                raise Exception("请至少传一个比特浏览器id")

            res = openBrowser(config.BIT_BROWSER_IDS[0])
            print(res)

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
                await self.ws.push({"isCompleted": True})
            finally:
                timestamp = datetime.now().strftime("%Y年%m月%d日_%H时%M分%S秒")
                driver.get_screenshot_as_file(f"screenshot_{timestamp}.png")
        except Exception as e:
            log.debug(
                f"发生异常:{e}，当前关键字：{self.word}",
                exc_info=True,
            )
            raise
