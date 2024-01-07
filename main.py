import json
import os
import re
import time
from datetime import datetime

import requests

# for selenium
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import selenium.common.exceptions as Exceptions

# for log
import logging
from rich.console import Console
from rich.logging import RichHandler

# for database
from database import get_session_maker
from models import Account
from sqlalchemy.exc import SQLAlchemyError

# for email and password generation
import petname
import secrets
import string

# for mail
import imaplib
import email as e_mail
import threading

# for retry
from retry import retry
from requests.exceptions import RequestException

# for configuration
from configurer import get_configuration

# ------------------------------------------------------------------------------------
# 初始化数据库（创建表）
DB_Session = get_session_maker('sqlite:///account.db')

# ------------------------------------------------------------------------------------
# 创建一个Rich的Console对象
console = Console()

# ------------------------------------------------------------------------------------

class Register:

    # site password
    xpath_site_password = "//label[text()='Password']/following-sibling::input[@id='password']"
    xpath_site_password_submit = "//button[@type='submit' and @name='action' and text()='Continue']"
    xpath_sign_up_link = "//a[@href='/auth/signup' and text()='Sign up']"

    # 输入生成的账号与密码
    xpath_account_email = "//input[@id='username' and @name='username' and preceding-sibling::label[text()='Email address']]"
    xpath_account_password = "//input[@id='password' and @name='password' and preceding-sibling::label[text()='Password']]"
    xpath_account_info_submit = "//button[@type='submit' and @name='action' and text()='Continue']"

    # 认证过程
    xpath_verify_button = "//button[@id='submit-token' and @type='submit']"
    xpath_verify_link_textarea = "//textarea[@aria-label='Please input the link']"
    xpath_verify_submit = "//div[@class='swal2-actions']//button[text()='OK']"

    # 注册时用户名
    xpath_signup_username_input = "//input[@name='username' and @id='username']"
    xpath_signup_username_submit = "//button[@type='submit' and @name='action' and text()='Continue']"

    # 拼图验证环节
    xpath_puzzle_button = "//button[text()='开始拼图']"

    # 注册成功
    xpath_sign_up_successful = "//h1[text()='Signup successful']"
    xpath_go_login = "//a[text()='Go log in']"

    # 登录环节
    xpath_login_email_input = "//input[@id='username']"
    xpath_login_password_input = "//input[@id='password']"
    xpath_login_submit = "//button[@type='submit' and @name='action' and text()='Continue']"

    # 起始页面引导
    xpath_ok_lets_go = "//div[text()='Okay, let’s go']"
    xpath_get_started = "//div[text()='Get started']"

    # 使用环节
    xpath_prompt_textarea = "//textarea[@id='prompt-textarea']"
    xpath_send_button_disabled = '//button[@data-testid="send-button" and @disabled]'


    def __init__(self, pandora_next_website, client_key, headless=False):

        self.logger = logging.getLogger(self.__class__.__name__)

        # chrome启动参数
        options = uc.ChromeOptions()

        options.add_argument('--incognito')
        # options.add_argument(f'--user-data-dir=./chatgpt_register')
        options.add_argument(f'--app={pandora_next_website}')

        self.logger.info('Loading undetected Chrome')

        # 检查是否已有 Patcher
        patched_driver = uc.Patcher().executable_path

        if not os.path.exists(patched_driver):
            self.logger.warning('No patched driver found!')
            patched_driver = None

        self.browser = uc.Chrome(
            # 如果不指定 executable_path 的位置，那么就会重复进行 Patch
            driver_executable_path=patched_driver,
            options=options,
            headless=headless
        )
        self.browser.set_page_load_timeout(120)

        # if not headless:
        self.browser.set_window_position(0, 0)  # 设置窗口位置
        self.browser.set_window_size(700, 900)  # 设置窗口大小

        self.browser.execute_script(
            f"window.localStorage.setItem('oai/apps/hasSeenOnboarding/chat', {datetime.today().strftime('%Y-%m-%d')});"
        )

        # 配置 Helper 与 Solver
        self.helper = SeleniumDriverHelper(self.browser)
        self.solver = FunCaptchaSolver(client_key, self.browser)

        self.logger.info('Loaded Undetected chrome')
        self.logger.info('Ready!')

    def pass_site_password(self, site_password):
        self.logger.info('Checking if site password exists...')

        site_password_input = self.helper.find_or_fail(By.XPATH, self.xpath_site_password, fail_ok=True)
        if site_password_input is None:
            self.logger.info('Site password does not exist. Passed.')
            return

        self.logger.info('Site password exists. Inputting password...')

        site_password_input.send_keys(site_password)

        self.logger.info('Looking for continue button to click...')

        continue_button = self.helper.find_or_fail(By.XPATH, self.xpath_site_password_submit)
        continue_button.click()

        self.logger.info('Password Submitted.')

    def click_signup_link(self):
        self.logger.info('Waiting for sign-up link appears...')

        signup_link = self.helper.sleepy_find_element(By.XPATH, self.xpath_sign_up_link)
        signup_link.click()

        self.logger.info('Sign-up link clicked.')

    def generate_account_information(self, email_postfix):

        # 生成不重复的账号与密码
        while (email := petname.generate(words=2, separator='_', letters=10) + email_postfix) \
                and self.check_account_exists(email):
            self.logger.warning(f'Generated repeated email{email}. Regenerating...')

        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for i in range(16))

        self.logger.info(f'Generated account: email({email}), password({password})')
        return email, password

    def input_email_and_password(self, email, password):
        self.logger.info('Waiting for email and password input appears...')

        email_input = self.helper.sleepy_find_element(By.XPATH, self.xpath_account_email)
        password_input = self.helper.sleepy_find_element(By.XPATH, self.xpath_account_password)

        self.logger.info('Inputting email and password...')

        email_input.send_keys(email)
        password_input.send_keys(password)

        self.logger.info('Looking for continue button to click...')

        continue_button = self.helper.find_or_fail(By.XPATH, self.xpath_account_info_submit)
        continue_button.click()

        self.logger.info('Account information submitted.')

    def input_verify_link(self, verify_link):
        self.logger.info('Waiting for verify button appears...')

        verify_button = self.helper.sleepy_find_element(By.XPATH, self.xpath_verify_button)
        verify_button.click()

        self.logger.info('Waiting for link textarea appears...')

        link_textarea = self.helper.sleepy_find_element(By.XPATH, self.xpath_verify_link_textarea)

        self.logger.info('Inputting verify link...')

        link_textarea.send_keys(verify_link)

        self.logger.info('Looking for OK button to click...')

        submit_button = self.helper.find_or_fail(By.XPATH, self.xpath_verify_submit)
        submit_button.click()

        self.logger.info('Verify link submitted.')

    def switch_to_puzzle_frame(self):
        self.logger.info('Switching to puzzle frame...')

        self.browser.switch_to.default_content()

        verification_frame = self.helper.sleepy_find_element(By.XPATH, '//iframe[@title="Verification challenge"]')
        self.browser.switch_to.frame(verification_frame)

        game_frame = self.helper.sleepy_find_element(By.XPATH, '//iframe[@id="game-core-frame"]')
        self.browser.switch_to.frame(game_frame)

        self.logger.info('Switched to puzzle frame.')

    def switch_to_default_frame(self):
        self.logger.info('Switching to default frame...')

        self.browser.switch_to.default_content()

        self.logger.info('Switched to default frame.')

    def wait_for_puzzle(self, question_type: str):

        self.switch_to_puzzle_frame()

        self.logger.info('Waiting for puzzle button appears...')

        time.sleep(2)
        puzzle_button = self.helper.sleepy_find_element(By.XPATH, self.xpath_puzzle_button)
        puzzle_button.click()

        self.logger.info('Puzzle button clicked.')

        self.logger.info('Waiting for puzzle to be solved...')

        self.solver.solve(question_type)

        self.switch_to_default_frame()

        self.helper.wait_until_appear(By.XPATH, self.xpath_sign_up_successful, timeout_duration=600)

        self.logger.info('Puzzle solved!')
        self.logger.info('Looking for login link to click...')

        login_button = self.helper.find_or_fail(By.XPATH, self.xpath_go_login)
        login_button.click()

        self.logger.info('Login button clicked.')

    def input_username(self, username):
        self.logger.info('Waiting for username input appears...')

        username_input = self.helper.sleepy_find_element(By.XPATH, self.xpath_signup_username_input)

        self.logger.info('Inputting username...')

        username_input.send_keys(username)

        self.logger.info('Looking for continue button to click...')

        continue_button = self.helper.find_or_fail(By.XPATH, self.xpath_signup_username_submit)
        continue_button.click()

        self.logger.info('Username submitted.')

    def login(self, username: str, password: str):
        self.logger.info('Waiting for email input appears...')

        self.helper.wait_until_appear(By.XPATH, self.xpath_login_email_input)

        # Find email textbox, enter e-mail
        email_box = self.helper.sleepy_find_element(By.XPATH, self.xpath_login_email_input)
        email_box.send_keys(username)
        self.logger.info('Filled email box')

        # Click continue
        continue_button = self.helper.sleepy_find_element(By.XPATH, self.xpath_login_submit)
        continue_button.click()
        self.logger.info('Clicked continue button')

        # Find password textbox, enter password
        pass_box = self.helper.sleepy_find_element(By.XPATH, self.xpath_login_password_input)
        pass_box.send_keys(password)
        self.logger.info('Filled password box')

        # Click continue
        time.sleep(0.5)
        continue_button = self.helper.sleepy_find_element(By.XPATH, self.xpath_login_submit)
        continue_button.click()
        self.logger.info('Logged in')

        # 等待进入界面
        self.logger.info('Waiting for prompt textarea appears...')
        self.helper.wait_until_appear(By.XPATH, self.xpath_prompt_textarea)

    def pass_tutorial(self):
        self.logger.info('Passing tutorial...')

        # 跳过引导（如果有的话）
        ok_lets_go = self.helper.sleepy_find_element(By.XPATH, self.xpath_ok_lets_go)
        ok_lets_go.click()
        self.logger.info('Passed "Okay, let\'s go".')

        get_started = self.helper.sleepy_find_element(By.XPATH, self.xpath_get_started)
        get_started.click()
        self.logger.info('Passed "Get started".')

    def interact(self, prompt):

        text_area = self.helper.find_or_fail(By.XPATH, self.xpath_prompt_textarea)

        # 使用 JavaScript 直接设置 textarea 的值
        self.logger.info('Sending message...')
        self.logger.info('Step.1 Click textarea.')
        text_area.click(); time.sleep(1.5);  # noqa
        self.logger.info('Step.2 Focus on textarea.')
        self.browser.execute_script("arguments[0].focus();", text_area, prompt); time.sleep(1);  # noqa
        self.logger.info('Step.3 Fill in textarea.')
        self.browser.execute_script("arguments[0].value = arguments[1];", text_area, prompt); time.sleep(1.5);  # noqa
        self.logger.info('Step.4 Add an additional ENTER.')
        text_area.send_keys(Keys.SHIFT + Keys.ENTER); time.sleep(1.5);  # noqa

        # 等待发送按钮出现
        self.logger.info('Step.5 Waiting for send button to appear.')
        self.helper.wait_until_disappear(By.XPATH, self.xpath_send_button_disabled); time.sleep(1);  # noqa
        text_area.send_keys(Keys.COMMAND + Keys.RETURN)
        self.logger.info('Step.6 Message sent, waiting for response')

        # 检查返回值
        pass

    def check_account_exists(self, email) -> bool:
        """检查指定email的账号是否存在"""
        with DB_Session() as session:
            try:
                account = session.query(Account).filter_by(email=email).first()
                if account:
                    self.logger.info(f"账号存在: {email}")
                    return True
                else:
                    self.logger.info(f"账号不存在: {email}")
                    return False
            except SQLAlchemyError as e:
                self.logger.error(f"数据库查询错误: {e}")
                raise

    def create_account(self, email, password):
        """创建新账号，如果账号已存在则抛出异常"""
        if self.check_account_exists(email):
            raise Exception("账号已存在")

        new_account = Account(email=email, password=password, is_active=1)

        with DB_Session() as session:
            try:
                session.add(new_account)
                session.commit()
                self.logger.info(f"创建账号成功: {email}")
            except SQLAlchemyError as e:
                self.logger.error(f"创建账号时出错: {e}")
                session.rollback()
                raise


class EmailMonitor:
    def __init__(self, server, port, username, password, folder, specified_sender, specified_receiver):
        self.server = server
        self.port = port
        self.username = username
        self.password = password
        self.folder = folder
        self.specified_sender = specified_sender
        self.specified_receiver = specified_receiver
        self.link_dict = dict()
        self.mail = None

        # 配置日志
        self.logger = logging.getLogger(self.__class__.__name__)

        # 线程
        self.thread = threading.Thread(target=self.check_new_mail, daemon=True)
        self.is_terminated = False

    def extract_link_from_mail(self, msg):
        # 实现从邮件内容提取链接的逻辑
        if msg.is_multipart():
            # Iterate over each part
            for part in msg.walk():
                # Check content type
                content_type = part.get_content_type()

                # Look for text/plain parts, but skip attachments
                if content_type == "text/html":
                    html_content = part.get_payload(decode=True).decode()

                    pattern = r'<a href="(.*?)".*?>[\s\S]*?Verify email address[\s\S]*?<\/a>'
                    result = re.search(pattern, html_content)
                    if result:
                        link = result.group(1)
                        self.logger.info(f'Account: {msg["To"]}')
                        self.logger.info(f'Found verify link: {link}')
                        return link
                    else:
                        self.logger.error('Verify link does not exist!')
                        return None
            else:
                self.logger.error(f'The text/html part not appears in this mail!')
                return None
        else:
            self.logger.error('The format of mail is wrong. Please check!')
            return None

    def check_new_mail(self):
        while not self.is_terminated:
            try:
                # 首次连接或重新连接
                if not self.mail:
                    self.mail = imaplib.IMAP4_SSL(self.server, self.port)
                    self.logger.info("Logging into Outlook mailbox...")
                    self.mail.login(self.username, self.password)
                    self.logger.info("Outlook successfully connected!")

                    # 列出所有文件夹
                    # status, folders = self.mail.list()
                    # if status == 'OK':
                    #     self.logger.info(f"Folders:")
                    #     for folder in folders:
                    #         self.logger.info('    ' + folder.decode())
                    # else:
                    #     self.logger.warning('列出所有Folders失败！')

                self.logger.info(f'Selecting folder: {self.folder}')
                self.mail.select(self.folder)

                # 搜索未读邮件
                self.logger.info(f'Searching for unseen mails...')
                # status, messages = self.mail.search(None, f'(UNSEEN FROM "{self.specified_sender}" TO "{self.specified_receiver}")')
                status, messages = self.mail.search(None, f'(FROM "{self.specified_sender}" TO "{self.specified_receiver}")')
                if status != 'OK':
                    self.logger.warning(f"Search failed，status: {status}")

                # Get the list of email IDs
                email_ids = messages[0].split()
                self.logger.info(f'Found {len(email_ids)} unseen mails from OpenAI.')

                # check if specific content appears
                for num in messages[0].split():
                    self.logger.info(f'Fetching unread mail -> {num.decode()}...')

                    # BUG: 使用 fetch RFC822 会将邮件标记为已读状态
                    status, data = self.mail.fetch(num, '(RFC822)')

                    if status == 'OK':
                        msg = e_mail.message_from_bytes(data[0][1])  # noqa

                        if msg['To'] == self.specified_receiver:
                            link = self.extract_link_from_mail(msg)
                            if link:
                                self.logger.info(f'[bold green]Got the verification mail for {self.specified_receiver}![/bold green]')
                                self.link_dict[msg['To']] = link

                                # 标记为已读
                                self.mail.store(num, '+FLAGS', '\\Seen')
                        else:
                            # 标记为未读
                            self.mail.store(num, '+FLAGS', '\\Unseen')
                            self.logger.info(f'Verification mail for {msg["To"]} discarded.')
                    else:
                        self.logger.error(f'Fetch failed for mail {num}!')

                self.logger.info("All emails have been checked.")
                time.sleep(2)

            except imaplib.IMAP4.error as e:
                self.logger.error(f"IMAP4错误: {e}")
                self.reset_connection()

            except Exception as e:
                self.logger.error(f"发生错误: {e}")
                self.reset_connection()

    def reset_connection(self):
        if self.mail:
            try:
                self.mail.close()
                self.mail.logout()
            except:
                pass
        self.mail = None
        self.logger.info("邮箱连接已重置")

    def start_monitoring(self):
        self.thread.start()
        self.logger.info("开始监控邮箱")

    def end_monitoring(self):
        self.is_terminated = True
        self.logger.info("Waiting for monitoring thread to end...")
        self.thread.join()
        self.logger.info('Monitoring thread ended.')

    def get_link(self, account):
        present = self.link_dict.get(account, None)
        self.logger.info(f"检查认证链接是否存在: {account} - {'存在' if present else '不存在'}")
        return present

    def remove_link(self, account):
        if account in self.link_dict:
            self.link_dict.pop(account)
            self.logger.info(f"账号已移除: {account}")
        else:
            self.logger.error(f"要移除的账号不存在: {account}")


class FunCaptchaSolver:

    def __init__(self, client_key,browser):

        # 配置 Capsolver ClientKey
        self.client_key = client_key

        # 配置浏览器 driver
        self.browser = browser
        self.helper = SeleniumDriverHelper(self.browser)

        # 配置日志
        self.logger = logging.getLogger(self.__class__.__name__)

    def solve(self, question_type: str):

        while True:
            previous_stage, (current_stage, total_stage) = None, self.get_stage_info()

            for i in range(total_stage):
                self.logger.info(f'({current_stage}/{total_stage}) [bold red]Solving puzzle...[/bold red]')

                # 是否是从头开始、或是已到达下一轮
                while current_stage == previous_stage:
                    current_stage, total_stage = self.get_stage_info()
                    time.sleep(1)
                previous_stage = current_stage

                puzzle_image = self.get_puzzle_image()
                solution = self.solve_puzzle(question_type, puzzle_image)
                self.switch_to_position(solution)
                self.submit_puzzle()

            if not self.try_again():
                self.logger.info(f'[bold green]Solve successful![/bold green]')
                break

            self.logger.warning(f'Solve failed. Try again!')


    def has_next_puzzle(self):
        self.logger.info('Detecting if has next puzzle...')

        submit_button = self.helper.sleepy_find_element(By.XPATH, "//button[text()='提交']", attempt_count=10, fail_ok=True)

        if submit_button:
            self.logger.info('Had next puzzle!')
            return True
        else:
            self.logger.info('Next puzzle does not appear in 10s.')
            return False

    @retry(tries=7, delay=1, backoff=2, exceptions=(Exceptions.StaleElementReferenceException,))
    def get_stage_info(self):
        self.logger.info('Detecting current stage information...')

        stage_label = self.helper.sleepy_find_element(By.XPATH, "//h2[contains(@class, 'text')]/span[@role='text']")
        match = re.search(r"\((\d+)，共 (\d+) 项\)", stage_label.text)

        if match:
            current_stage = int(match.group(1))
            total_stage = int(match.group(2))
            return current_stage, total_stage

        raise ValueError(stage_label.text)

    def try_again(self):
        self.logger.info('Detecting if has try again button...')

        try_again_button = self.helper.sleepy_find_element(By.XPATH, "//button[text()='再次尝试']", attempt_count=5, fail_ok=True)

        if try_again_button:
            self.logger.info('Need to try again!')
            return True
        else:
            self.logger.info('Try again button does not appear in 10s.')
            return False

    def start_puzzle(self):
        self.logger.info('Starting puzzle...')

        start_puzzle = self.helper.sleepy_find_element(By.XPATH, "//button[text()='开始拼图']")
        start_puzzle.click()

        self.logger.info('Puzzle started!')

    def submit_puzzle(self):
        self.logger.info('Submitting puzzle...')

        submit_puzzle = self.browser.find_element(By.XPATH, "//button[text()='提交']")
        submit_puzzle.click()

        self.logger.info('Puzzle submitted!')

    def switch_to_position(self, target):
        self.logger.info(f'Switching to target position: {target}')

        while (curr_position := self.find_active_child_index()) != target:
            self.logger.info(f'Current position: {curr_position}, moving...')
            self.right_arrow()
            time.sleep(1)

        self.logger.info('Switched to target position!')

    def right_arrow(self):
        self.logger.info('Clicking right arrow...')

        right_arrow = self.browser.find_element(By.XPATH, '//a[@role="button" and contains(@class, "right-arrow")]')
        right_arrow.click()

    @retry(tries=7, delay=1, backoff=2, exceptions=(ValueError, AttributeError))
    def get_puzzle_image(self):

        # 定位到img元素
        image_element = self.helper.sleepy_find_element(By.XPATH, "//div[contains(@class, 'answer-frame')]/div[contains(@class, 'box')]/img")

        # 获取style属性
        style_attribute = image_element.get_attribute("style")

        # 提取background-image的URL
        image_url = re.search(r"background-image: url\((.*?)\)", style_attribute).group(1)[6:][:-1]
        self.logger.info(f'Extracted puzzle image url: {image_url}')

        # 构建并执行JavaScript
        script = """
        var callback = arguments[arguments.length - 1]; // 获取callback函数
        var imageUrl = arguments[0]; // 获取图片URL
        fetch(imageUrl)
            .then(response => response.blob())
            .then(blob => {
                var reader = new FileReader();
                reader.onloadend = () => callback(reader.result); // 读取完成后调用callback
                reader.readAsDataURL(blob);
            })
            .catch(error => {
                console.error('Fetch error:', error);
                callback(''); // 发生错误时也要调用callback
            });
        """
        image_data = self.browser.execute_async_script(script, 'blob:' + image_url).split('image/jpeg;base64,')[-1]

        if len(image_data) < 1024:
            self.logger.error(f'Got invalid image_data, retrying...')
            raise ValueError

        self.logger.info('Successfully extracted puzzle image data!')

        return image_data

    def find_active_child_index(self):

        # 定位父标签
        parent_element = self.browser.find_element(By.XPATH, '//div[contains(@class, "pip-container")]')
        # 获取所有子标签
        children = parent_element.find_elements(By.XPATH, "./*")

        # 遍历子标签，检查 class 属性中是否包含 active
        for index, child in enumerate(children):
            if "active" in child.get_attribute("class"):
                return index
        return None

    @retry(tries=5, delay=1, backoff=2, exceptions=(RequestException, json.JSONDecodeError, ValueError, KeyError))
    def solve_puzzle(self, question_type: str, base64_str: str):
        self.logger.info(f'Solving puzzle...')

        url = 'https://api.capsolver.com/createTask'

        payload = {
            "clientKey": self.client_key,
            "task": {
                "type": "FunCaptchaClassification",
                "images": [
                    base64_str
                ],
                # "module": "train_coorinatesmatch",
                "question": question_type
            }
        }

        res = requests.post(url, json=payload)

        self.logger.info(f'Puzzle solved. Solution: {res.json()["solution"]}')

        return res.json()['solution']['objects'][0]


class SeleniumDriverHelper:
    """
    Tool class to afford convenience.
    """

    def __init__(self, driver):

        # 配置浏览器 driver
        self.browser = driver

        # 配置日志
        self.logger = logging.getLogger(self.__class__.__name__)

    def sleepy_find_element(self, by, query, attempt_count: int = 30, sleep_duration: int = 5, fail_ok: bool = False):
        """
        Finds the web element using the locator and query.

        This function attempts to find the element multiple times with a specified
        sleep duration between attempts. If the element is found, the function returns the element.

        Args:
            by (selenium.webdriver.common.by.By): The method used to locate the element.
            query (str): The query string to locate the element.
            attempt_count (int, optional): The number of attempts to find the element. Default: 20.
            sleep_duration (int, optional): The duration to sleep between attempts. Default: 1.

        Returns:
            selenium.webdriver.remote.webelement.WebElement: Web element or None if not found.
        """
        for _count in range(attempt_count):
            item = self.browser.find_elements(by, query)
            if len(item) > 0:
                item = item[0]
                self.logger.debug(f'Element {query} has found')
                break
            self.logger.debug(f'Element {query} is not present, attempt: {_count+1}')
            time.sleep(sleep_duration)
        else:
            if fail_ok:
                self.logger.debug(f'Element {query} is not found.')
                return None
            self.logger.error(f'Element {query} is not found.')
            raise Exceptions.NoSuchElementException(f'Element {query} is not found.')
        return item

    def wait_until_disappear(self, by, query, timeout_duration=60):
        """
        Waits until the specified web element disappears from the page.

        This function continuously checks for the presence of a web element.
        It waits until the element is no longer present on the page.
        Once the element has disappeared, the function returns.

        Args:
            by (selenium.webdriver.common.by.By): The method used to locate the element.
            query (str): The query string to locate the element.
            timeout_duration (int, optional): The total wait time before the timeout exception. Default: 15.

        Returns:
            None
        """
        self.logger.debug(f'Waiting element {query} to disappear.')
        try:
            WebDriverWait(
                self.browser,
                timeout_duration
            ).until_not(
                EC.presence_of_element_located((by, query))  # noqa
            )
            self.logger.debug(f'Element {query} disappeared.')
        except Exceptions.TimeoutException:
            self.logger.debug(f'Element {query} still here, something is wrong.')
            raise
        return

    def wait_until_appear(self, by, query, timeout_duration=60):
        """
        Waits until the specified web element appears on the page.

        This function continuously checks for the presence of a web element.
        It waits until the element is present on the page.
        Once the element appears, the function returns.

        Args:
            by (selenium.webdriver.common.by.By): The method used to locate the element.
            query (str): The query string to locate the element.
            timeout_duration (int, optional): The total wait time before the timeout exception. Default: 15.

        Returns:
            None
        """
        self.logger.debug(f'Waiting for element {query} to appear.')
        try:
            WebDriverWait(
                self.browser,
                timeout_duration
            ).until(
                EC.presence_of_element_located((by, query))  # noqa
            )
            self.logger.debug(f'Element {query} appeared.')
        except Exceptions.TimeoutException:
            self.logger.error(f'Element {query} did not appear within {timeout_duration} seconds.')
            raise
        return

    def find_or_fail(self, by, query, return_elements=False, fail_ok=False):
        """
        Finds a list of elements given query, if none of the items exists, throws an error

        Args:
            by (selenium.webdriver.common.by.By): The method used to locate the element.
            query (str): The query string to locate the element.

        Returns:
            selenium.webdriver.remote.webelement.WebElement: Web element or None if not found.
        """
        dom_element = self.browser.find_elements(by, query)
        if not dom_element:
            if not fail_ok:
                self.logger.error(f'{query} is not located. Please raise an issue with verbose=True')
            return None

        self.logger.debug(f'{query} is located.')
        if return_elements:
            return dom_element
        else:
            return dom_element[0]



if __name__ == '__main__':

    # 配置日志，使用RichHandler
    logging.basicConfig(
        level="INFO",  # 设置日志级别
        format="%(message)s",  # 设置日志格式
        datefmt="%Y/%m/%d %H:%M:%S",  # 设置时间格式
        handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True, show_path=False)]  # 使用RichHandler
    )
    log = logging.getLogger(__name__)

    config = get_configuration()

    # 从配置字典中获取值
    headless_browser = config.get('headless_browser', True)
    account_postfix = config.get('account_postfix')
    client_key = config.get('client_key')
    pandora_next_website = config.get('pandora_next_website')
    site_password = config.get('site_password', '')
    IMAP_server = config.get('IMAP_server')
    IMAP_port = config.get('IMAP_port', 993)
    email_username = config.get('email_username')
    email_password = config.get('email_password')
    email_folder = config.get('email_folder', 'Inbox')
    puzzle_type = config.get('puzzle_type', 'train_coordinates')  # 有多种类型，可在 capsolver 网站查看

    if account_postfix and not account_postfix.startswith('@'):
        account_postfix = '@' + account_postfix

    # 检查配置
    if not all([account_postfix, client_key, pandora_next_website, IMAP_server, email_username, email_password, email_folder, puzzle_type]):
        log.critical('Please review your environment variable configurations!')
        exit(-1)

    # 模拟注册类
    register = Register(
        pandora_next_website=pandora_next_website,
        client_key=client_key,
        headless=headless_browser
    )

    # 跳过 site_password
    register.pass_site_password(site_password)

    # 点击注册按钮
    register.click_signup_link()

    # 通过给定邮箱后缀生成账号密码
    email, password = register.generate_account_information(account_postfix)

    # 输入注册需要的账号密码
    register.input_email_and_password(email, password)

    # 进行邮件监测
    monitor = EmailMonitor(
        server=IMAP_server,
        port=IMAP_port,
        username=email_username,
        password=email_password,
        folder=email_folder,
        specified_sender='noreply@tm.openai.com',
        specified_receiver=email
    )
    # start to monitor mails
    monitor.start_monitoring()

    count = 0
    while (link := monitor.get_link(email)) is None and count < 15:
        count += 1
        log.info(f'账号[{email}]认证链接仍不存在，等待中...({count})')
        time.sleep(3)

    if link:
        log.info(f'已获取到账号[{email}]的认证链接！')
    else:
        log.critical(f'邮箱获取失败！')
        exit(-1)

    # 结束邮件监测
    monitor.end_monitoring()

    # 填写认证链接
    register.input_verify_link(link)

    # 设置账号用户名
    register.input_username(email.split('@')[0])

    # 等待 puzzle 出现并解决
    register.wait_for_puzzle(question_type=puzzle_type)

    # 在数据库中创建账号密码
    register.create_account(email, password)

    # 登录测试
    register.login(email, password)

    # 跳过引导
    register.pass_tutorial()

    # 发送问题
    register.interact('Hello! How are you?')

    # 等待生成
    time.sleep(10)

    # 关闭
    register.browser.close()
    register.browser.quit()

