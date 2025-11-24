from time import sleep
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from random import randint
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin

import os
import random

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

options = Options()

user_data_dir = os.path.join(os.getcwd(), "browser_data", "dy_user_data_dir")
options.add_argument(f"--user-data-dir={user_data_dir}")  # 用户数据路径

options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(options)
driver.maximize_window()
driver.get("https://www.douyin.com")

active = driver.find_element(By.CSS_SELECTOR, '#dy-modal-video-container-search_multi_modal [data-e2e="feed-active-video"]')
commentList = active.find_elements(By.CSS_SELECTOR, '[data-e2e="comment-list"] > div')
