# Google パスワードマネージャー & Google 同期実装ガイド

Helium ブラウザ for Windows に Google パスワードマネージャーと Google クラウド同期を統合するための完全なドキュメントです。

## 📋 概要

このドキュメントは、以下の機能を Helium ブラウザに追加するための実装ガイドです：

- ✅ Google パスワードマネージャーからのパスワード読み込み
- ✅ ブラウザ内でのパスワード管理・保存
- ✅ Google アカウントへのクラウド同期（双方向）
- ✅ Google Sign-In による認証

---

## 🔧 実装済みコンポーネント

### 1. **GN ビルドフラグ設定** (`flags.windows.gn`)

```gn
# Google Password Manager and Sync support
enable_sync=true
enable_signin=true
enable_dice_support=true
google_build=true
```

**効果:**
- Chromium の同期機能を有効化
- Google Sign-In フレームワークを有効化
- DICE (Device Identity and Credential Exchange) 対応

---

### 2. **パスワード管理機能有効化パッチ**

**ファイル:** `patches/helium/core/enable-google-password-sync.patch`

**変更内容:**
- `kCredentialsEnableService`: `false` → `true` (パスワード保存サービス有効化)
- `kCredentialsEnableAutosignin`: `false` → `true` (自動サインイン有効化)
- `kAutofillProfileEnabled`: `false` → `true` (プロフィール自動入力有効化)
- `kAutofillCreditCardEnabled`: `false` → `true` (クレジットカード自動入力有効化)

---

### 3. **Google Sign-In 有効化パッチ**

**ファイル:** `patches/helium/core/enable-google-signin.patch`

**変更内容:**
```gni
# コンポーネント: components/signin/public/base/signin_buildflags.gni
enable_signin = true        # Google Sign-In 有効化
enable_dice_support = true  # DICE プロトコル対応
google_build = true         # Google 固有機能有効化
```

---

### 4. **クラウド同期サービス有効化パッチ**

**ファイル:** `patches/helium/core/enable-sync-service.patch`

**変更内容:**
- `SyncServiceImpl::IsSyncFeatureEnabled()`: ユーザー設定に基づいて同期を有効化
- `SyncUserSettings::IsSyncAllowedByPlatform()`: `false` → `true`

---

### 5. **OAuth 2.0 統合パッチ**

**ファイル:** `patches/helium/core/google-oauth-integration.patch`

**新規関数:**
```cpp
std::string GetOAuthClientId();     // OAuth Client ID 取得
std::string GetOAuthClientSecret(); // OAuth Client Secret 取得
```

**環境変数対応:**
```bash
GOOGLE_API_KEY          # Google API キー
GOOGLE_CLIENT_ID        # OAuth 2.0 Client ID
GOOGLE_CLIENT_SECRET    # OAuth 2.0 Client Secret
```

---

## 🚀 ビルド・セットアップ手順

### ステップ 1: 前提条件

```bash
# Windows 10 以上
# Visual Studio 2022 またはそれ以降
# Python 3.8+
# Git
```

### ステップ 2: リポジトリのクローン

```bash
git clone --recurse-submodules https://github.com/subaru8523/helium-windows.git
cd helium-windows
git checkout feature/google-password-sync
```

### ステップ 3: Google API キー取得

1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新しいプロジェクトを作成
3. 以下の API を有効化：
   - Google Identity
   - Google Drive API
4. OAuth 2.0 認証情報を作成（デスクトップアプリケーション）
5. Client ID と Client Secret を記録

### ステップ 4: 環境変数設定

```cmd
# Developer Command Prompt for VS で実行
set GOOGLE_API_KEY=YOUR_API_KEY
set GOOGLE_CLIENT_ID=YOUR_CLIENT_ID
set GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
```

### ステップ 5: ビルド実行

```bash
python3 build.py
python3 package.py
```

---

## 📝 機能説明

### パスワード管理フロー

```
1. ユーザーがサイトにアクセス
   ↓
2. ブラウザがログイン情報を検出
   ↓
3. ユーザーに保存を提案
   ↓
4. ローカルに保存 + Google アカウントに同期
   ↓
5. 他のデバイスで利用可能
```

### Google Sign-In フロー

```
1. 設定 > アカウント > Google アカウント
   ↓
2. ユーザーが「サインイン」をクリック
   ↓
3. Google 認証ページ（ブラウザで表示）
   ↓
4. 認証成功 → 同期開始
   ↓
5. パスワード・ブックマーク・履歴が同期
```

---

## ⚙️ 設定 & カスタマイズ

### デフォルト設定の変更

**ファイル:** `patches/helium/core/enable-google-password-sync.patch`

パスワード保存をデフォルト無効にしたい場合：

```patch
-      kCredentialsEnableService, true,
+      kCredentialsEnableService, false,
```

### 同期対象の選択

Chromium の設定で、以下のデータ型の同期を制御可能：

- ✅ パスワード
- ✅ ブックマーク
- ✅ 履歴
- ✅ 開いているタブ
- ✅ 設定

---

## 🔒 セキュリティ考慮事項

### データ暗号化

Google Sync では以下が暗号化されて送信されます：

- **エンドツーエンド暗号化 (E2EE):**
  - パスワード ✅
  - 支払い情報 ✅

- **トランスポート層暗号化 (TLS):**
  - ブックマーク
  - 履歴
  - 設定

### ローカルストレージ

```
%LOCALAPPDATA%\Helium\User Data\
├── Default\
│   ├── Login Data      # 暗号化されたパスワード
│   ├── Sync Data       # 同期メタデータ
│   └── prefs           # ユーザー設定
```

### プライバシー設定

**設定 > プライバシーとセキュリティ > Google パスワードマネージャー**

- パスワード保存を有効/無効
- 自動サインイン有効/無効
- 漏洩パスワード通知

---

## 🧪 テスト方法

### ユニットテスト実行

```bash
# パスワードマネージャー テスト
python3 -m pytest tests/password_manager_test.py

# 同期サービス テスト
python3 -m pytest tests/sync_service_test.py

# OAuth 統合 テスト
python3 -m pytest tests/oauth_integration_test.py
```

### 機能テスト

1. **パスワード保存テスト**
   - ログインフォームに入力
   - ブラウザに保存提案が表示される
   - 保存後にブラウザが自動入力する

2. **Google Sign-In テスト**
   - 設定 > アカウント > Google アカウント
   - ログイン情報が正しく同期される

3. **データ同期テスト**
   - 複数のデバイスでログイン
   - パスワード追加時に別デバイスで同期確認

---

## 📊 トラブルシューティング

### ビルドエラー

**エラー:** `enable_signin is not defined`

**解決策:**
```bash
# patches/helium/core/enable-google-signin.patch が正しく適用されているか確認
grep -r "enable_signin = true" build/src/
```

### 同期が開始されない

**エラー:** Google アカウントでサインインしても同期されない

**チェックリスト:**
```bash
# 1. ネットワーク接続確認
ping accounts.google.com

# 2. API キー確認
echo %GOOGLE_CLIENT_ID%

# 3. ログファイル確認
cat %LOCALAPPDATA%\Helium\chrome_debug.log
```

### パスワード読み込み失敗

**エラー:** Google パスワードマネージャーからインポートできない

**解決策:**
1. Google アカウントの 2 段階認証を確認
2. アプリパスワードを生成: https://myaccount.google.com/apppasswords
3. ブラウザを再起動

---

## 🔄 アップデート & メンテナンス

### Chromium バージョン更新時

```bash
# 1. helium-chromium submodule をアップデート
git submodule update --remote

# 2. パッチの再検証
python3 devutils/validate_patches.py --local build/src

# 3. 必要に応じてパッチを修正
./devutils/update_patches.sh merge
```

### Google API 認証情報の更新

```bash
# OAuth 認証情報が期限切れになった場合
# 1. https://console.cloud.google.com にアクセス
# 2. 新しい Client Secret を生成
# 3. 環境変数を更新
set GOOGLE_CLIENT_SECRET=NEW_SECRET
```

---

## 📚 参考資料

### Chromium ドキュメント
- [Password Manager](https://source.chromium.org/chromium/chromium/src/+/main:components/password_manager/)
- [Sync Service](https://source.chromium.org/chromium/chromium/src/+/main:components/sync/)
- [Sign-In](https://source.chromium.org/chromium/chromium/src/+/main:components/signin/)

### Google API ドキュメント
- [OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
- [Google API Client Library](https://developers.google.com/api-client-library)

### Helium リソース
- [Helium Main Repository](https://github.com/imputnet/helium)
- [Helium macOS Build Guide](https://github.com/imputnet/helium-macos/blob/main/docs/building.md)

---

## 📝 ライセンス

このパッチセットは GPL-3.0 ライセンス下で公開されています。

詳細は [LICENSE](../LICENSE) を参照してください。

---

## 👥 貢献

改善提案やバグ報告は GitHub Issues でお願いします：

https://github.com/subaru8523/helium-windows/issues

---

**最終更新:** 2026-07-01
**バージョン:** 1.0.0
**ステータス:** ✅ 実装完了
