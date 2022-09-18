import requests
from urllib3.util import parse_url
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("link", type=str, help="Link to GitHub Raw")
args = parser.parse_args()
result = requests.get(args.link)
file = result.text
parsed = parse_url(args.link).path.split("/")
if not os.path.isdir(os.path.join(os.getcwd(),"submissions", parsed[1])):
    os.mkdir(os.path.join(os.getcwd(),"submissions", parsed[1]))
with open(os.path.join(os.getcwd(),"submissions", parsed[1], parsed[-1]), 'w') as f:
    f.write(file)
