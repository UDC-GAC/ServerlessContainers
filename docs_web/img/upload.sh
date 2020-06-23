#!/usr/bin/env bash
bash convert_svg_to_png.sh
aws s3 cp logo.png s3://jonatan.enes.udc/serverless_containers_website/logo_serverless.png --acl public-read
aws s3 cp icon.png s3://jonatan.enes.udc/serverless_containers_website/icon_serverless.png --acl public-read