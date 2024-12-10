from flask import Flask, render_template, request, redirect, url_for, session
import requests
from coinbase.wallet.client import OAuthClient

app = Flask(__name__)
app.secret_key = "bruh123"

CLIENT_ID = "e353dee5-5b3d-4856-9b74-493be0a0a356"
CLIENT_SECRET = "-PUVajYqH0j6~OO-1FhEXaLN1N"
CALLBACK_URL = "http://127.0.0.1/consumer_auth"
AUTH_URI = "https://www.coinbase.com/oauth/authorize"
TOKEN_URI = "https://www.coinbase.com/oauth/token"
SCOPES = "wallet:accounts:read,wallet:transactions:read,wallet:transactions:send"


@app.route('/')
def home():
    """Home page with OAuth link."""
    auth_url = (
        f"{AUTH_URI}?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={CALLBACK_URL}"
        f"&scope={SCOPES}"
    )
    return render_template('index.html', auth_url=auth_url)


@app.route('/consumer_auth')
def receive_token():
    """Handle Coinbase OAuth callback."""
    oauth_code = request.args.get('code')
    if not oauth_code:
        return render_template("error.html", message="Authorization failed: No code received.")

    # Exchange  authorization code for  access token
    data = {
        "grant_type": "authorization_code",
        "code": oauth_code,
        "redirect_uri": CALLBACK_URL,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    response = requests.post(TOKEN_URI, data=data)

    if response.status_code != 200:
        return render_template("error.html", message="Token exchange failed. Try again later.")

    token_data = response.json()
    session['access_token'] = token_data.get("access_token")
    session['refresh_token'] = token_data.get("refresh_token")

    # Redirect to dashboard
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    """Logs the user out by clearing the session and redirecting to the home page."""
    session.clear()  # Clear all session data
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    access_token = session.get('access_token')
    if not access_token:
        return redirect(url_for('home'))

    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    response = requests.get("https://api.coinbase.com/v2/user", headers=headers)

    return render_template('dashboard.html')



@app.route('/tax_loss')
def tax_loss_page():
    """Tax Loss Harvesting Page."""
    if 'access_token' not in session:
        return redirect(url_for('home'))

    #TOP 10 CYRPTOS ON COINBASE, SHOULD MAKE CRYPTOS THE USER HOLDS
    top_10_cryptos = [
        {"name": "Bitcoin", "currency": "BTC"},
        {"name": "Ethereum", "currency": "ETH"},
        {"name": "Tether", "currency": "USDT"},
        {"name": "Solana", "currency": "SOL"},
        {"name": "BNB", "currency": "BNB"},
        {"name": "XRP", "currency": "XRP"},
        {"name": "Dogecoin", "currency": "DOGE"},
        {"name": "USD Coin", "currency": "USDC"},
        {"name": "Cardano", "currency": "ADA"},
        {"name": "TRON", "currency": "TRX"},
    ]

    # Initialize Coinbase client
    client = OAuthClient(session['access_token'], session['refresh_token'])

    # Fetch and calculate cost basis and current price
    currencies_with_data = []
    for crypto in top_10_cryptos:
        currency = crypto["currency"]
        try:
            current_price = get_current_price(currency)
            cost_basis = calculate_cost_basis(client, currency)
            crypto.update({"current_price": current_price, "cost_basis": cost_basis})
        except Exception as e:
            crypto.update({"current_price": "N/A", "cost_basis": "N/A", "error": str(e)})

        currencies_with_data.append(crypto)

    return render_template("tax_loss.html", currencies=currencies_with_data)


@app.route('/tax_loss/<currency>')
def run_tax_loss(currency):
    """Run Tax Loss Harvesting for a Specific Currency."""
    if 'access_token' not in session:
        return redirect(url_for('home'))

    # Initialize Coinbase client
    client = OAuthClient(session['access_token'], session['refresh_token'])
    try:
        # Perform tax loss harvesting for the selected currency
        result = tax_loss_harvesting(client, currency)
        return render_template("tax_loss_result.html", currency=currency, result=result)
    except Exception as e:
        print(f"Error running tax loss harvesting: {e}")
        return render_template("error.html", message=f"Error running tax loss harvesting: {e}")


def tax_loss_harvesting(client, currency):
    """Performs tax loss harvesting for a given currency."""
    try:
        accounts = client.get_accounts()
        account = next(
            acc for acc in accounts['data']
            if acc['balance']['currency'] == currency and float(acc['balance']['amount']) > 0
        )
    except StopIteration:
        return f"No balance available for {currency}. Cannot perform tax loss harvesting."

    try:
        current_price = get_current_price(currency)
        cost_basis = calculate_cost_basis(client, currency)

        if current_price < cost_basis:
            amount_to_sell = float(account['balance']['amount'])
            # Sell the cryptocurrency
            sell_result = client.sell(account['id'], {
                "amount": str(amount_to_sell),
                "currency": currency,
                "payment_method": None
            })
            return f"Sold {amount_to_sell} {currency} at ${current_price} to harvest losses."
        else:
            return f"No losses to harvest for {currency}."
    except Exception as e:
        return f"Error during tax loss harvesting: {e}"



def calculate_cost_basis(client, currency):
    """
    Calculates the cost basis for a given currency in a user's Coinbase account.
    """
    try:
        print("Fetching accounts...")
        accounts = client.get_accounts()
        print(f"Accounts retrieved: {accounts}")

        # Select account with non-zero balance and wallet type
        account = next(
            acc for acc in accounts['data'] 
            if acc['balance']['currency'] == currency 
            and float(acc['balance']['amount']) > 0 
            and acc['type'] == "wallet"
        )
        print(f"Account for {currency} found: {account}")

        transactions = client.get_transactions(account['id'])
        print(f"Transactions retrieved: {transactions}")

        total_cost = 0.0
        total_units = 0.0

        for txn in transactions['data']:
            print(f"Processing transaction: {txn}")
            if txn['type'] == 'buy':
                units_acquired = float(txn['amount']['amount'])
                cost_in_native = float(txn['native_amount']['amount'])
                total_cost += cost_in_native
                total_units += units_acquired

        if total_units == 0:
            return f"No {currency} acquired."

        cost_basis = total_cost / total_units
        return round(cost_basis, 2)

    except StopIteration:
        return f"No account found for {currency}."
    except Exception as e:
        return f"Error fetching cost basis for {currency}: {e}"


def get_current_price(currency):
    """Fetches the current price of the given currency."""
    url = f"https://api.coinbase.com/v2/prices/{currency}-USD/spot"
    response = requests.get(url)
    price_data = response.json()
    return float(price_data['data']['amount'])


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)





