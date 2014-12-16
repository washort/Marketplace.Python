import argparse
import json
import os
import urlparse

from marketplace import Client

import logging
logging.basicConfig(level=logging.DEBUG)

def main():
    parser = argparse.ArgumentParser(
        description='Reviewer onboarding data loader')
    parser.add_argument('url', type=str,
                        help='url of marketplace')
    parser.add_argument('apiKey', type=str,
                        help='api key to use')
    parser.add_argument('apiSecret', type=str,
                        help='api secret')
    args = parser.parse_args()
    scheme, netloc = urlparse.urlparse(args.url)[:2]
    domain, _, port = netloc.partition(':')
    c = Client(
        domain=domain, protocol=scheme,
        port=int(port) if port else 80,
        consumer_key=args.apiKey,
        consumer_secret=args.apiSecret)
    appdir = os.path.join(os.path.dirname(__file__), 'reviewer_apps')
    apps = [json.load(open(os.path.join(appdir, appf)))
            for appf in os.listdir(appdir)
            if appf.endswith('.json')]

    def validate(url):
        response = c.validate_manifest(url)
        if response.status_code == 201:
            return json.loads(response.content)['id']
        else:
            raise RuntimeError('Failed to submit app %s for validation: %s' % (
                url, response.status_code))

    validation_ids = [validate(app['manifest_url']) for app in apps]
    pending = set(validation_ids)
    while pending:
        for manifest_id in list(pending):
            response = c.get_manifest_validation_result(manifest_id)
            if response.status_code != 200:
                raise RuntimeError('Validation failure %s: %s' % (
                    manifest_id, response.status_code))
            else:
                content = json.loads(response.content)
                if content['processed']:
                    if content['valid']:
                        pending.remove(manifest_id)
                    else:
                        raise RuntimeError('Validation failed %s: %s' % (
                            manifest_id, content))

    appids = []

    def creat(validation_id):
        response = c.create(validation_id)
        content = json.loads(response.content)
        if response.status_code != 201:
            raise RuntimeError("Failed to create app %s: %s" % (
                validation_id, response.status_code))
        return content['id']
    appids = [creat(vid) for vid in validation_ids]

    for (app_id, app) in zip(appids, apps):
        response = c.update(
            app_id,
            {
                'name': 'App %d' % (app_id,),
                'summary': 'App %d' % (app_id,),
                'categories': app['categories'],
                'support_email': 'app-reviewers@mozilla.org',
                'device_types': app['device_types'],
                'privacy_policy': app['privacy_policy'],
                'premium_type': 'free',
            })
        if response.status_code != 202:
            raise RuntimeError("App update failed %s: %s" % (
                app_id, response.status_code))

        c.create_screenshot(app_id, os.path.join(appdir, "screenshot.png"))
        c.add_content_ratings(app_id, 0, 0)
