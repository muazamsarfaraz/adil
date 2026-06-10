FROM nginx:alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY index.html /usr/share/nginx/html/index.html
COPY accessibility.html /usr/share/nginx/html/accessibility.html
COPY find-a-solicitor.html /usr/share/nginx/html/find-a-solicitor.html
COPY favicon.ico /usr/share/nginx/html/favicon.ico
COPY images/ /usr/share/nginx/html/images/
# data/solicitors.json is fetched by the embedded finder widget at /data/solicitors.json.
# Must ship in the image — previously omitted, causing the widget to load but
# return no search results (nginx served the 404-fallback index.html as
# "JSON" which broke the parser).
COPY data/ /usr/share/nginx/html/data/
ENV PORT=80
EXPOSE 80
CMD ["/bin/sh", "-c", "envsubst '${PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
