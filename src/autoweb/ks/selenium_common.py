import time
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.remote.webelement import WebElement
from ..tools import log as logger



# ==================== 滚动操作 ====================

def scroll_page(driver, scroll_times=3, scroll_distance=500, delay_range=(0.5, 1.5)):
    """
    模拟滚轮操作，向下滚动页面
    Args:
        driver: Selenium WebDriver 对象
        scroll_times: 滚动次数，默认3次
        scroll_distance: 每次滚动的距离（像素），默认500
        delay_range: 每次滚动之间的延迟范围（秒），默认0.5-1.5秒
    """
    for i in range(scroll_times):
        # 使用 JavaScript 模拟滚轮向下滚动
        driver.execute_script(f"window.scrollBy(0, {scroll_distance});")
        logger.info(f"第 {i+1} 次滚动，滚动距离: {scroll_distance}px")
        # 随机延迟，模拟人类操作
        time.sleep(random.uniform(delay_range[0], delay_range[1]))


def scroll_to_element(driver, element):
    """
    滚动到指定元素位置
    Args:
        driver: Selenium WebDriver 对象
        element: 要滚动到的元素
    """
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
    time.sleep(0.5)


def scroll_to_bottom(driver):
    """
    滚动到页面底部
    Args:
        driver: Selenium WebDriver 对象
    """
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(0.5)


def scroll_element_down(driver, element, scroll_distance=50, scroll_times=1, delay_range=(0.3, 0.8)):
    """
    指定元素向下滚动
    Args:
        driver: Selenium WebDriver 对象
        element: 要滚动的元素
        scroll_distance: 每次滚动的距离（像素），默认50
        scroll_times: 滚动次数，默认1次
        delay_range: 每次滚动之间的延迟范围（秒），默认0.3-0.8秒
    """
    for i in range(scroll_times):
        # 先滚动到元素位置
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(0.2)
        # 在元素位置基础上向下滚动
        driver.execute_script(f"window.scrollBy(0, {scroll_distance});")
        logger.info(f"第 {i+1} 次元素向下滚动，滚动距离: {scroll_distance}px")
        # 随机延迟，模拟人类操作
        if i < scroll_times - 1:  # 最后一次不需要延迟
            time.sleep(random.uniform(delay_range[0], delay_range[1]))


def scroll_element_inner(driver, element, is_loop=False, scroll_distance=50, scroll_times=1, delay_range=(0.3, 3)):
    """
    在指定元素内部向下滚动（适用于有滚动条的元素）
    Args:
        driver: Selenium WebDriver 对象
        element: 要滚动的元素（必须是有滚动条的元素）
        is_loop: 是否死循环滚动，直到没有评论为止，默认False
        scroll_distance: 每次滚动的距离（像素），默认50
        scroll_times: 滚动次数，默认1次（当is_loop为True时此参数无效）
        delay_range: 每次滚动之间的延迟范围（秒），默认0.3-3秒
    """
    if is_loop:
        count = 0
        while True:
            count += 1
            # 在元素内部滚动
            driver.execute_script(f"arguments[0].scrollTop += {scroll_distance};", element)
            logger.info(f"第 {count} 次元素内部向下滚动，滚动距离: {scroll_distance}px")
            # 随机延迟，模拟人类操作
            time.sleep(random.uniform(delay_range[0], delay_range[1]))
    else:
        for i in range(scroll_times):
            # 在元素内部滚动
            driver.execute_script(f"arguments[0].scrollTop += {scroll_distance};", element)
            logger.info(f"第 {i+1} 次元素内部向下滚动，滚动距离: {scroll_distance}px")
            # 随机延迟，模拟人类操作
            if i < scroll_times - 1:  # 最后一次不需要延迟
                time.sleep(random.uniform(delay_range[0], delay_range[1]))

def scroll_element_down_js(driver, element, scroll_distance=50, scroll_times=1, delay_range=(0.3, 0.8)):
    """
    指定元素向下滑动js脚本
    Args:
        driver: Selenium WebDriver 对象
        element: 要滑动的元素
        scroll_distance: 每次滑动的距离（像素），默认50
        scroll_times: 滑动次数，默认1次
        delay_range: 每次滑动之间的延迟范围（秒），默认0.3-0.8秒
    """
    if element is None:
        logger.info("元素为空，无法执行滚动")
        return False

    success = True
    for i in range(scroll_times):
        try:
            # 先将元素滚动到可视区域
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(random.uniform(0.15, 0.3))

            scrolled = driver.execute_script(
                """
                const target = arguments[0];
                const distance = arguments[1];

                const dispatchWheel = (el, delta) => {
                    let event;
                    if (typeof WheelEvent === 'function') {
                        event = new WheelEvent('wheel', {deltaY: delta, bubbles: true, cancelable: true});
                    } else {
                        event = document.createEvent('MouseEvents');
                        event.initEvent('wheel', true, true);
                        event.deltaY = delta;
                    }
                    try {
                        el.dispatchEvent(event);
                    } catch (err) {
                        // 忽略事件派发异常，不影响滚动
                    }
                };

                const scrollWindow = (delta) => {
                    const before = window.pageYOffset || document.documentElement.scrollTop || 0;
                    window.scrollBy(0, delta);
                    const after = window.pageYOffset || document.documentElement.scrollTop || 0;
                    return Math.abs(after - before) > 0;
                };

                const scrollElement = (el, delta) => {
                    if (!el || el === document.body || el === document.documentElement) {
                        return scrollWindow(delta);
                    }
                    const before = el.scrollTop;
                    el.scrollTop = before + delta;
                    return Math.abs(el.scrollTop - before) > 0;
                };

                dispatchWheel(target, distance);

                const canScrollElement = target && target !== document.body && target !== document.documentElement &&
                    target.scrollHeight > (target.clientHeight || 0);

                if (canScrollElement) {
                    const scrolledElement = scrollElement(target, distance);
                    if (scrolledElement) {
                        return true;
                    }
                }

                return scrollWindow(distance);
                """,
                element,
                scroll_distance
            )

            logger.info(f"第 {i + 1} 次元素向下滚动（JS），滚动距离: {scroll_distance}px，结果: {'成功' if scrolled else '未滚动'}")
        except Exception as e:
            success = False
            logger.info(f"元素JS向下滚动失败 (尝试 {i + 1}/{scroll_times}): {e}")

        if i < scroll_times - 1:
            time.sleep(random.uniform(delay_range[0], delay_range[1]))

    return success


# ==================== 点击操作 ====================

def safe_click(driver, element, max_retries=3):
    """
    安全点击元素，尝试多种方式
    Args:
        driver: Selenium WebDriver 对象
        element: 要点击的元素
        max_retries: 最大重试次数，默认3次
    Returns:
        bool: 是否点击成功
    """
    try:
        # 先滚动到元素位置
        scroll_to_element(driver, element)
        time.sleep(random.uniform(0.2, 0.5))
        
        # 尝试普通点击
        element.click()
        return True
    except Exception as e:
        try:
            # 尝试JavaScript点击
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception as js_e:
            logger.info(f"点击失败 (尝试 尝试JavaScript点击): {e}, JavaScript点击也失败: {js_e}")
            time.sleep(random.uniform(0.5, 1.0))
    return False


def click_with_delay(driver, element, delay_range=(0.5, 1.5)):
    """
    点击元素并添加随机延迟，模拟人类操作
    Args:
        driver: Selenium WebDriver 对象
        element: 要点击的元素
        delay_range: 点击后的延迟范围（秒），默认0.5-1.5秒
    Returns:
        bool: 是否点击成功
    """
    result = safe_click(driver, element)
    if result:
        time.sleep(random.uniform(delay_range[0], delay_range[1]))
    return result


# ==================== 输入操作 ====================

def human_type(element, text, delay_range=(0.1, 0.3)):
    """
    模拟人类输入，逐字符输入并添加随机延迟
    Args:
        element: 输入框元素
        text: 要输入的文本
        delay_range: 每个字符之间的延迟范围（秒），默认0.1-0.3秒
    """
    # 先清空输入框
    element.clear()
    time.sleep(random.uniform(0.1, 0.2))
    
    # 逐字符输入
    for char in text:
        element.send_keys(char)
        # 随机延迟，模拟人类输入速度
        time.sleep(random.uniform(delay_range[0], delay_range[1]))


def type_with_backspace(element, text, backspace_probability=0.1, delay_range=(0.1, 0.3)):
    """
    模拟人类输入，偶尔按退格键（更真实）
    Args:
        element: 输入框元素
        text: 要输入的文本
        backspace_probability: 按退格键的概率，默认0.1（10%）
        delay_range: 每个字符之间的延迟范围（秒），默认0.1-0.3秒
    """
    from selenium.webdriver.common.keys import Keys
    
    element.clear()
    time.sleep(random.uniform(0.1, 0.2))
    
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(delay_range[0], delay_range[1]))
        
        # 随机按退格键（模拟输入错误后删除）
        if random.random() < backspace_probability:
            element.send_keys(Keys.BACKSPACE)
            time.sleep(random.uniform(0.1, 0.2))
            element.send_keys(char)  # 重新输入
            time.sleep(random.uniform(delay_range[0], delay_range[1]))


# ==================== 等待操作 ====================

def wait_for_element(driver, by, value, timeout=10, poll_frequency=0.5):
    """
    等待元素出现
    Args:
        driver: Selenium WebDriver 对象
        by: 定位方式（By.ID, By.CLASS_NAME等）
        value: 定位值
        timeout: 超时时间（秒），默认10秒
        poll_frequency: 轮询频率（秒），默认0.5秒
    Returns:
        WebElement: 找到的元素，如果超时返回None
    """
    try:
        element = WebDriverWait(driver, timeout, poll_frequency=poll_frequency).until(
            EC.presence_of_element_located((by, value))
        )
        return element
    except TimeoutException:
        logger.info(f"等待元素超时: {by}={value}")
        return None


def wait_for_clickable(driver, by, value, timeout=10, poll_frequency=0.5):
    """
    等待元素可点击
    Args:
        driver: Selenium WebDriver 对象
        by: 定位方式
        value: 定位值
        timeout: 超时时间（秒），默认10秒
        poll_frequency: 轮询频率（秒），默认0.5秒
    Returns:
        WebElement: 找到的元素，如果超时返回None
    """
    try:
        element = WebDriverWait(driver, timeout, poll_frequency=poll_frequency).until(
            EC.element_to_be_clickable((by, value))
        )
        return element
    except TimeoutException:
        logger.info(f"等待元素可点击超时: {by}={value}")
        return None


def wait_for_elements(driver, by, value, timeout=10, min_count=1, poll_frequency=0.5):
    """
    等待多个元素出现
    Args:
        driver: Selenium WebDriver 对象
        by: 定位方式
        value: 定位值
        timeout: 超时时间（秒），默认10秒
        min_count: 最少元素数量，默认1个
        poll_frequency: 轮询频率（秒），默认0.5秒
    Returns:
        list: 找到的元素列表，如果数量不足返回空列表
    """
    try:
        elements = WebDriverWait(driver, timeout, poll_frequency=poll_frequency).until(
            lambda d: d.find_elements(by, value) if len(d.find_elements(by, value)) >= min_count else False
        )
        return elements if elements else []
    except TimeoutException:
        logger.info(f"等待元素超时: {by}={value}, 最少需要 {min_count} 个")
        return []


# ==================== 随机延迟 ====================

def random_delay(min_seconds=0.5, max_seconds=1.5):
    """
    随机延迟，模拟人类操作间隔
    Args:
        min_seconds: 最小延迟（秒），默认0.5秒
        max_seconds: 最大延迟（秒），默认1.5秒
    """
    time.sleep(random.uniform(min_seconds, max_seconds))


def human_delay(delay_type='normal'):
    """
    根据操作类型返回合适的延迟时间
    Args:
        delay_type: 延迟类型
            - 'short': 短延迟（0.1-0.3秒）
            - 'normal': 正常延迟（0.5-1.5秒）
            - 'long': 长延迟（1.0-3.0秒）
            - 'thinking': 思考延迟（2.0-5.0秒）
    """
    delay_ranges = {
        'short': (0.1, 0.3),
        'normal': (0.5, 1.5),
        'long': (1.0, 3.0),
        'thinking': (2.0, 5.0)
    }
    delay_range = delay_ranges.get(delay_type, delay_ranges['normal'])
    time.sleep(random.uniform(delay_range[0], delay_range[1]))


# ==================== 鼠标移动 ====================

def move_to_element(driver, element, smooth=True):
    """
    移动鼠标到元素位置（模拟人类鼠标移动）
    Args:
        driver: Selenium WebDriver 对象
        element: 目标元素
        smooth: 是否平滑移动，默认True
    """
    from selenium.webdriver.common.action_chains import ActionChains
    
    try:
        actions = ActionChains(driver)
        if smooth:
            # 先移动到元素附近，再移动到元素
            location = element.location
            size = element.size
            # 添加一些随机偏移，模拟人类鼠标移动
            offset_x = random.randint(-10, 10)
            offset_y = random.randint(-10, 10)
            actions.move_by_offset(offset_x, offset_y)
        actions.move_to_element(element)
        actions.perform()
        time.sleep(random.uniform(0.1, 0.3))
    except Exception as e:
        logger.info(f"移动鼠标到元素失败: {e}")


# ==================== 元素查找 ====================

def find_element_safe(driver, by, value, timeout=5, retry_times=3):
    """
    安全查找元素，带重试机制
    Args:
        driver: Selenium WebDriver 对象
        by: 定位方式
        value: 定位值
        timeout: 每次查找的超时时间（秒），默认5秒
        retry_times: 重试次数，默认3次
    Returns:
        WebElement: 找到的元素，如果失败返回None
    """
    for attempt in range(retry_times):
        try:
            element = wait_for_element(driver, by, value, timeout)
            if element:
                return element
        except Exception as e:
            logger.info(f"查找元素失败 (尝试 {attempt + 1}/{retry_times}): {e}")
            if attempt < retry_times - 1:
                time.sleep(random.uniform(0.5, 1.0))
    return None


def find_elements_safe(driver, by, value, timeout=5, min_count=1, retry_times=3):
    """
    安全查找多个元素，带重试机制
    Args:
        driver: Selenium WebDriver 对象
        by: 定位方式
        value: 定位值
        timeout: 每次查找的超时时间（秒），默认5秒
        min_count: 最少元素数量，默认1个
        retry_times: 重试次数，默认3次
    Returns:
        list: 找到的元素列表，如果失败返回空列表
    """
    for attempt in range(retry_times):
        try:
            elements = wait_for_elements(driver, by, value, timeout, min_count)
            if elements and len(elements) >= min_count:
                return elements
        except Exception as e:
            logger.info(f"查找元素失败 (尝试 {attempt + 1}/{retry_times}): {e}")
            if attempt < retry_times - 1:
                time.sleep(random.uniform(0.5, 1.0))
    return []

def is_element_visible(driver, elements: list[WebElement]) -> list[WebElement]:
    """
    判断多个元素是否在可视范围内
    Args:
        driver: Selenium WebDriver 对象
        elements: 要判断的元素列表
    Returns:
        list: 在可视范围内的元素列表
    """
    visible_elements = []
    for element in elements:
        try:
            # 检查元素是否存在且可见
            if element.is_displayed():
                # 获取元素位置和大小
                location = element.location
                size = element.size
                
                # 获取浏览器窗口大小
                window_size = driver.get_window_size()
                window_width = window_size['width']
                window_height = window_size['height']
                
                # 获取当前滚动位置
                scroll_x = driver.execute_script("return window.pageXOffset;")
                scroll_y = driver.execute_script("return window.pageYOffset;")
                
                # 计算元素在页面中的实际位置
                element_top = location['y']
                element_bottom = element_top + size['height']
                element_left = location['x']
                element_right = element_left + size['width']
                
                # 计算可视区域
                viewport_top = scroll_y
                viewport_bottom = scroll_y + window_height
                viewport_left = scroll_x
                viewport_right = scroll_x + window_width
                
                # 判断元素是否在可视区域内
                # 元素至少有一部分在可视区域内即可
                if (element_bottom > viewport_top and 
                    element_top < viewport_bottom and 
                    element_right > viewport_left and 
                    element_left < viewport_right):
                    visible_elements.append(element)
        except Exception as e:
            # 如果检查元素时出现异常，跳过该元素
            continue
    
    return visible_elements
