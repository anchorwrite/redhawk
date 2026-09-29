FROM python:3.13-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home learner && mkdir /app/.lab && chown learner /app/.lab
COPY redhawk/ /app/redhawk/
USER learner
EXPOSE 8787
CMD ["python", "-m", "redhawk", "serve", "--host", "0.0.0.0"]
