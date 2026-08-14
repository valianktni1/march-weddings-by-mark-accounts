# Build stage
FROM node:20-alpine as build

WORKDIR /app

# Copy package metadata and install from the source manifest. The original
# Emergent repository did not contain its referenced yarn.lock.
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund

# Copy source
COPY . .

# Build arguments for environment variables
ARG REACT_APP_BACKEND_URL=
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

# Build the app
RUN yarn build

# Production stage
FROM nginx:alpine

# Copy build output
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
