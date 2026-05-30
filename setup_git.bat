@echo off
chcp 65001 >nul
echo ========================================
echo  DealRadar GitHub 初始化脚本
echo ========================================
echo.

cd /d "%~dp0"

REM 清理上次残留的 .git
if exist ".git" (
    echo 清理旧的 .git 目录...
    rmdir /s /q ".git"
)

REM 初始化仓库
echo 初始化 Git 仓库...
git init -b main
git config user.email "shihaowei49@gmail.com"
git config user.name "shihao"

REM 添加所有文件
echo 添加文件...
git add .
git commit -m "init: dealradar site + auto-update workflow"

echo.
echo ========================================
echo 请先在 GitHub 新建一个仓库（不要勾选 README）
echo 然后把仓库地址填入下面，按回车继续
echo 例如：https://github.com/shihao/dealradar.git
echo ========================================
set /p REPO_URL="请输入你的 GitHub 仓库地址: "

git remote add origin %REPO_URL%
git push -u origin main

echo.
echo ========================================
echo 完成！代码已推送到 GitHub
echo 接下来去 Cloudflare Pages 绑定这个仓库即可
echo ========================================
pause
