import argparse
import configparser
import getpass
import os
import re
import shutil
import sys
import warnings
from datetime import datetime, date
import posixpath
from urllib.parse import urlparse

import requests
import requests.exceptions
from bs4 import BeautifulSoup
from rich.console import Console
from tqdm import TqdmExperimentalWarning
from tqdm.rich import tqdm

_DEFAULT_CONFIG = '/usr/local/etc/kattisrc'


class ConfigError(Exception):
    pass


def get_url(cfg, option="", default=""):
    if cfg.has_option('kattis', option):
        return cfg.get('kattis', option)
    else:
        return 'https://%s/%s' % (cfg.get('kattis', 'hostname'), default)


def get_config():
    """Returns a ConfigParser object for the .kattisrc file(s)
    """
    cfg = configparser.ConfigParser()
    if os.path.exists(_DEFAULT_CONFIG):
        cfg.read(_DEFAULT_CONFIG)

    if not cfg.read([os.path.join(os.path.expanduser("~"), '.kattisrc'),
                     os.path.join(os.path.dirname(sys.argv[0]), '.kattisrc')]):
        raise ConfigError('''\
I failed to read in a config file from your home directory or from the
same directory as this script. To download a .kattisrc file please visit
https://<kattis>/download/kattisrc
The file should look something like this:
[user]
username: yourusername
token: *********
[kattis]
hostname: <kattis>
loginurl: https://<kattis>/login
submissionurl: https://<kattis>/submit
submissionsurl: https://<kattis>/submissions''')
    return cfg


def login(login_url, username, password=None, token=None):
    """Log in to Kattis.
    At least one of password or token needs to be provided.
    Returns a requests.Response with cookies needed to be able to submit
    """
    login_args = {'user': username, 'script': 'true'}
    if password:
        login_args['password'] = password
    if token:
        login_args['token'] = token

    return requests.post(login_url, data=login_args)


def login_from_config(cfg):
    """Log in to Kattis using the access information in a kattisrc file
    Returns a requests.Response with cookies needed to be able to submit
    """
    username = cfg.get('user', 'username')
    password = token = None
    try:
        password = cfg.get('user', 'password')
    except configparser.NoOptionError:
        pass
    try:
        token = cfg.get('user', 'token')
    except configparser.NoOptionError:
        pass
    if password is None and token is None:
        raise ConfigError('''\
Your .kattisrc file appears corrupted. It must provide a token (or a
KATTIS password).
Please download a new .kattisrc file''')

    loginurl = get_url(cfg, 'loginurl', 'login')
    return login(loginurl, username, password, token)


if __name__ == "__main__":
    FOLDER_ROOT = os.path.dirname(__file__)
    SUBMISSION_DIR = os.path.join(os.getcwd(), "submissions")
    DT_FORMAT = "%Y-%m-%d %H:%M"

    today = date.today()

    parser = argparse.ArgumentParser()
    parser.add_argument("link", type=str, help="Link to Kattis Standings")
    parser.add_argument("-p", action="store_true")
    parser.add_argument("-q", type=str, default="A")
    args = parser.parse_args()
    standings_link = args.link

    console = Console()

    if re.match("(https?://)?.*\.kattis\.com/.*/problems/?", standings_link):
        standings_link = posixpath.join(posixpath.dirname(standings_link), "standings")
    elif not re.match("(https?://)?.*\.kattis\.com/.*/standings/?", standings_link):
        console.print("[red] Please input a link of a valid Kattis Standing Page")
        sys.exit(1)

    warnings.filterwarnings("ignore", category=TqdmExperimentalWarning)
    if args.p:
        kattis_domain = input("Kattis Domain: ").lower().strip()
        user = input("Username: ").strip()
        pswd = getpass.getpass()
        try:
            login_reply = login(f"https://{kattis_domain}.kattis.com/login", username=user, password=pswd)
        except requests.exceptions.RequestException as err:
            print('Login connection failed:', err)
            sys.exit(1)
    else:
        with console.status("[green]Retrieving Login Information"):
            try:
                cfg = get_config()
            except ConfigError as exc:
                print(exc)
                sys.exit(1)
        console.print("[green]Login Information Retrieved")

        with console.status("[green]Logging In"):
            try:
                login_reply = login_from_config(cfg)
            except requests.exceptions.RequestException as err:
                print('Login connection failed:', err)
                sys.exit(1)
        user = cfg.get('user', 'username')

    if not login_reply.status_code == 200:
        print('Login failed.')
        if login_reply.status_code == 403:
            print('Incorrect username or password/token (403)')
        elif login_reply.status_code == 404:
            print('Incorrect login URL (404)')
        else:
            print('Status code:', login_reply.status_code)
        sys.exit(1)

    login_cookies = login_reply.cookies

    console.print(f"[green]Logged in as [white]{user}")

    with console.status("[green]Retrieving Assignments and Students") as status:
        standings = requests.get(standings_link, cookies=login_cookies)
        plain_standings = standings.content.decode('utf-8').replace('<br />', '\n')
        soup = BeautifulSoup(plain_standings, 'html.parser')
        try:
            start_time = datetime.strptime(
                " ".join(soup.find(attrs={"class": "contest-start"}).getText().split()[1:-1]),
                DT_FORMAT)
        except ValueError:
            start_time = datetime.strptime(
                " ".join(soup.find(attrs={"class": "contest-start"}).getText().split()[1:-1]),
                "%H:%M")
            start_time = start_time.replace(year=today.year, month=today.month, day=today.day)
        try:
            end_time = datetime.strptime(
                " ".join(soup.find(attrs={"class": "contest-end"}).getText().split()[1:-1]),
                DT_FORMAT)
        except ValueError:
            end_time = datetime.strptime(
                " ".join(soup.find(attrs={"class": "contest-end"}).getText().split()[1:-1]),
                "%H:%M")
            end_time = end_time.replace(year=today.year, month=today.month, day=today.day)
        table = soup.find(attrs={"class": "standings-table"})
        question = ord(args.q.upper()[0]) - ord("A"[0])
        assignment = table.find("thead").find_all("a")[question]
        student_list = table.find_all_next("tr")[1:-1]

        accepted = set()
        attempted = set()
        no_submission = set()

        for student in student_list:
            username = student.find("a").getText().strip()
            solve = student.find(attrs={"class": "standings-cell-score"}).find_all_next("td")[question]
            if solve.get("class") is None:
                no_submission.add(username)
            elif "attempted" in solve.get("class"):
                attempted.add(username)
            elif "solved" in solve.get("class"):
                accepted.add(username)
            elif "first" in solve.get("class"):
                accepted.add(username)
            else:
                raise RuntimeError
    console.print(f"[green]Retrieved Assignments and Students")

    student_list = accepted.union(attempted).union(no_submission)

    page = 0
    submission_dict = {}
    red_plagiarism = set()
    yellow_plagiarism = set()
    late_submission = set()
    loop = True

    problem = os.path.basename(os.path.normpath(urlparse(assignment.get("href")).path))
    with console.status(f"[green]Retrieving Submissions for [white]{problem} [green]from "
                        f"[white]{start_time.strftime(DT_FORMAT)}"):
        while loop:
            if args.p:
                result = requests.get(f"https://{kattis_domain}.kattis.com/submissions",
                                      params={"problem": problem, "language": "Java", "page": page, "status": "AC"},
                                      cookies=login_cookies)
            else:
                result = requests.get(get_url(cfg, 'submissionsurl', 'submissions'),
                                      params={"problem": problem, "language": "Java", "page": page, "status": "AC"},
                                      cookies=login_cookies)
            page += 1
            plain_result = result.content.decode('utf-8').replace('<br />', '\n')
            soup = BeautifulSoup(plain_result, 'html.parser')
            submissions = soup.find(id="judge_table").tbody.find_all_next("tr")
            for submission in submissions:
                if submission.get("class") is not None and "testcases-row" in submission.get("class"):
                    continue
                id_ = submission.get("data-submission-id")
                try:
                    submit_time = datetime.strptime(submission.find(attrs={"data-type": "time"}).getText(),
                                                    "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    submit_time = datetime.strptime(submission.find(attrs={"data-type": "time"}).getText(), "%H:%M:%S")
                    submit_time = submit_time.replace(year=today.year, month=today.month, day=today.day)
                if submit_time < start_time:
                    loop = False
                    break

                try:
                    author = submission.find(attrs={"data-type": "author"}).find("a").getText().strip()
                except AttributeError:
                    continue
                if author in student_list:
                    if submit_time > end_time and author in no_submission:
                        late_submission.add(author)

                    if author in accepted:
                        submission_dict[author] = id_.strip()

                    red_flag = bool(submission.find(attrs={"class": "plagiarism-warning-high"}))
                    if red_flag:
                        red_plagiarism.add(author)

                    yellow_flag = bool(submission.find(attrs={"class": "plagiarism-warning"}))
                    if yellow_flag:
                        yellow_plagiarism.add(author)
    console.print(f"[green]All Submissions for [white]{problem} [green]from " +
                  f"[white]{start_time.strftime(DT_FORMAT)} [green]Retrieved")

    submission_id_list = submission_dict.values()

    missing_submission = []
    try:
        if len(os.listdir(SUBMISSION_DIR)) == 0:
            console.print(f"[red]Warning: Submission Folder is Empty")
        else:
            for submission in tqdm(os.listdir(SUBMISSION_DIR), desc="Removing redundant submissions"):
                if submission not in submission_id_list and os.path.isdir(os.path.join(SUBMISSION_DIR, submission)):
                    shutil.rmtree(os.path.join(SUBMISSION_DIR, submission))
            for id_ in submission_id_list:
                if id_ not in os.listdir(SUBMISSION_DIR):
                    missing_submission.append(author)
            if len(missing_submission) > 0:
                console.print(f"[red]Submissions Missing: {missing_submission}")
    except FileNotFoundError:
        console.print(f"[red]Warning: Submission Folder Not Found")

    console.rule(f"[green]Analysis Report")
    console.print(f"[red]Red Plagiarism Notices: {sorted(red_plagiarism)}")
    console.print(f"[yellow]Yellow Plagiarism Notices: {sorted(yellow_plagiarism.difference(red_plagiarism))}")
    console.print(f"[cyan]Early Submission : {sorted(set(accepted).difference(submission_dict.keys()))}")
    console.print(f"[blue]Late Submission: {sorted(late_submission)}")
    console.print(f"[magenta]Attempted Only: {sorted(attempted.difference(late_submission))}")
    console.print(f"[white]No Submission: {sorted(no_submission.difference(late_submission))}")

    with open(os.path.join(os.getcwd(),f"{problem}_{datetime.now().strftime('%y%m%d%H%M%S')}.txt"), "w") as fp:
        fp.write(f"Red Plagiarism Notices: {sorted(red_plagiarism)}\n")
        fp.write(f"Yellow Plagiarism Notices: {sorted(yellow_plagiarism.difference(red_plagiarism))}\n")
        fp.write(f"Early Submission : {sorted(set(accepted).difference(submission_dict.keys()))}\n")
        fp.write(f"Late Submission: {sorted(late_submission)}\n")
        fp.write(f"Attempted Only: {sorted(attempted.difference(late_submission))}\n")
        fp.write(f"No Submission: {sorted(no_submission.difference(late_submission))}\n")