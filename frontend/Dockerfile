# 阶段 1: 构建 Vue (使用 Node 20 Alpine)
FROM node:20-alpine as build-stage
WORKDIR /app
COPY package*.json ./
# 如果遇到依赖安装网络问题，可以取消下面这行的注释使用淘宝源
# RUN npm config set registry https://registry.npmmirror.com
RUN npm install
COPY . .
RUN npm run build

# 阶段 2: 生产环境 Nginx (使用 Alpine)
FROM nginx:alpine as production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]