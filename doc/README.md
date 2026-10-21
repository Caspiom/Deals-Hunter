# 📖 Guia de Configuração: Notificações & Telegram (@BotFather)
# 📖 Setup Guide: Desktop Notifications & Telegram (@BotFather)

🌍 **Idioma / Language:** [🇧🇷 Português](#-português-passo-a-passo) | [🇺🇸 English](#-english-step-by-step)

---

## 🇧🇷 Português — Passo a Passo

O **Deals Hunter** funciona de duas formas (você pode usar uma ou ambas ao mesmo tempo):
1. **Notificações Nativas no PC** *(Ativado por padrão — Zero configuração)*
2. **Bot no Telegram via `@BotFather`** *(Opcional — Receba alertas no celular e controle o bot de qualquer lugar)*

---

### 1️⃣ Notificações Direto no PC
- Já vêm **ativadas por padrão** (`DESKTOP_NOTIFICATIONS=true`).
- Quando uma promoção abaixo do seu preço-alvo é encontrada, um alerta aparece no canto da tela.
- **Clique na notificação** (ou no botão *"Abrir Oferta no Navegador"*) para abrir a página da promoção imediatamente.
- Para testar se o seu sistema está exibindo alertas, abra as **Configurações (⚙)** no canto inferior do painel e clique em **Testar**.

---

### 2️⃣ Como Configurar o Telegram (`@BotFather`)

Se você quiser receber as promoções no seu celular pelo Telegram, siga este passo a passo rápido (leva menos de 1 minuto):

#### Passo 1: Criar o seu Bot no `@BotFather`
1. Abra o Telegram e acesse o bot oficial **[@BotFather](https://t.me/BotFather)** (verifique o selo azul de verificado).
2. Envie o comando:
   ```text
   /newbot
   ```
3. O `@BotFather` vai pedir um **nome de exibição** para o seu bot. Digite qualquer nome, por exemplo:
   ```text
   Meu Deals Hunter
   ```
4. Em seguida, ele vai pedir um **nome de usuário (username)** que **obrigatoriamente precisa terminar em `bot`**, por exemplo:
   ```text
    gappy_deals_hunter_bot
   ```
5. Pronto! O `@BotFather` enviará uma mensagem com o seu **HTTP API Token**, parecido com isto:
   ```text
   1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```

#### Passo 2: Colar o Token no Deals Hunter
1. Abra o painel do **Deals Hunter** (na barra do Noctalia, Bandeja do Sistema ou rodando `python main.py --gui`).
2. Clique no ícone de **Configurações (`⚙`)** no canto inferior do painel.
3. Cole o seu **Bot Token** no campo **`Bot Token (@BotFather)`** e clique em **Salvar**.

#### Passo 3: Vincular seu Chat ID automaticamente
1. No Telegram, clique no link do bot que você acabou de criar (na mensagem do `@BotFather`) e clique em **Começar** (ou envie `/start`).
2. O **Deals Hunter** detectará automaticamente o seu `Chat ID` na primeira mensagem `/start`, salvará no seu arquivo `.env` e responderá confirmando o vínculo!
   - *(Opcional)* Se preferir preencher o `Chat ID` manualmente, você pode descobrir seu ID enviando uma mensagem para o [@userinfobot](https://t.me/userinfobot) e colar no campo **Chat ID**.

---

### 💬 Comandos Disponíveis no Telegram
Depois de configurado, você também pode controlar sua lista pelo celular:
- `/start` — Vincula seu Chat ID e mostra o menu de ajuda
- `/add Nome do Produto | Preço Máx` — Ex: `/add Galaxy S24 | 2500`
- `/list` — Lista todos os produtos monitorados na sua Watchlist
- `/del <ID>` — Remove um produto pelo ID
- `/check` — Força uma varredura imediata nas lojas

---
---

## 🇺🇸 English — Step-by-Step

**Deals Hunter** supports two notification channels (you can use either one or both together):
1. **Native PC Desktop Notifications** *(Enabled by default — Zero configuration)*
2. **Telegram Bot via `@BotFather`** *(Optional — Get instant alerts on your phone and control your watchlist remotely)*

---

### 1️⃣ Native PC Desktop Notifications
- **Enabled by default** (`DESKTOP_NOTIFICATIONS=true`).
- Whenever a deal drops below your target price, a native desktop notification pops up on your screen.
- **Click the notification** to open the deal page directly in your default web browser.
- To test desktop alerts, click the **Settings (`⚙`)** button at the bottom corner of the panel and click **Test**.

---

### 2️⃣ How to Set Up Telegram (`@BotFather`)

If you also want to receive deal alerts on your phone via Telegram, follow these 3 quick steps (takes under 1 minute):

#### Step 1: Create your Bot with `@BotFather`
1. Open Telegram and start a chat with the official **[@BotFather](https://t.me/BotFather)** (look for the blue verified checkmark).
2. Send the command:
   ```text
   /newbot
   ```
3. `@BotFather` will ask for a **display name** for your bot. Type any name you like, e.g.:
   ```text
   My Deals Hunter
   ```
4. Next, it will ask for a **username** that **must end with `bot`**, for example:
   ```text
   my_deals_hunter_bot
   ```
5. Done! `@BotFather` will reply with your **HTTP API Token**, which looks like:
   ```text
   1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
   ```

#### Step 2: Paste the Token in Deals Hunter
1. Open the **Deals Hunter** panel (from the Noctalia bar, System Tray, or by running `python main.py --gui`).
2. Click the **Settings (`⚙`)** icon in the bottom corner of the panel.
3. Paste your **Bot Token** into the **`Bot Token (@BotFather)`** field and click **Save**.

#### Step 3: Auto-Link your Chat ID
1. In Telegram, open the chat with your newly created bot and press **Start** (or send `/start`).
2. **Deals Hunter** will automatically detect your personal `Chat ID` on the first `/start` message, save it to `.env`, and reply confirming your account is linked!
   - *(Optional)* If you want to enter your `Chat ID` manually, you can get it from [@userinfobot](https://t.me/userinfobot) and paste it into the **Chat ID** field.

---

### 💬 Available Telegram Commands
Once linked, you can manage your watchlist from anywhere:
- `/start` — Links your Chat ID and displays the help menu
- `/add Product Name | Max Price` — Example: `/add Galaxy S24 | 2500`
- `/list` — Lists all products in your Watchlist
- `/del <ID>` — Removes a product by its ID
- `/check` — Forces an immediate price check across stores
