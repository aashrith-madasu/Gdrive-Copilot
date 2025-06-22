BACKEND_URL = "http://localhost:8000"

// On popup load
chrome.storage.local.get(["username", "userId"], (data) => {
  if (data.username) {
    document.getElementById("login-page").hidden = true;
    document.getElementById("user").innerHTML = `User : ${data.username}`;
  } else {
    document.getElementById("main-page").hidden = true;
  }
});


function authenticate() {

  const authUrl = new URL("https://accounts.google.com/o/oauth2/auth");
  authUrl.searchParams.set("client_id", "609825494443-r36gpv0vjf0s7r2q680e1h89n90a48tj.apps.googleusercontent.com");
  authUrl.searchParams.set("redirect_uri", `https://${chrome.runtime.id}.chromiumapp.org`);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", "https://www.googleapis.com/auth/drive.readonly");
  authUrl.searchParams.set("access_type", "offline");
  authUrl.searchParams.set("prompt", "consent");

  console.log(authUrl.href)
  
  chrome.identity.launchWebAuthFlow(
    {
      url: authUrl.href,
      interactive: true
    },
    (redirectUrl) => {
      if (chrome.runtime.lastError) {
        console.error(chrome.runtime.lastError.message);
        return;
      }

      console.log("Sucesssss", redirectUrl);

      // Parse token from redirectUrl
      const params = new URLSearchParams(new URL(redirectUrl).search);
      const code = params.get("code");
      console.log("OAuth Code:", code);

      sendCode(code);
    }
  );
}

function sendCode(code) {
  
    fetch("http://localhost:8000/auth", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: `${code}` })
    })
    .then(res => res.json())
    .then(data => {
      console.log("sendCode response : ", data)
    })
}


function refreshIngestionStatus() {

    fetch("http://localhost:8000/ingestion_status", {
        method: "GET",
    })
    .then(res => res.json())
    .then(data => {
      console.log("ingestion status response: ", data)

      document.getElementById("status").innerHTML = `<strong> Documents ingested : ${data.ingestion_status} </strong>`

      for (let i in data.files) {
        const file = data.files[i];

        const option = document.createElement("option");
        option.value = file
        option.textContent = file;

        document.getElementById("selected-file").appendChild(option);
      }
    })

}

function submitQuery() {

  const query = document.getElementById("query").value;

  fetch("http://localhost:8000/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query })
  })
  .then(res => res.json())
  .then(data => {
    console.log("search response: ", data)

    var final_result_str = data.response

    final_result_str = final_result_str.replace(/<cite>(.*?)<\/cite>/g, '<span class="citation">$1</span>');

    document.getElementById("results").innerHTML = final_result_str
  })

}

async function handleLogin() {

  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  const res = await fetch(`${BACKEND_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });

  const result = await res.json();
  const resultEl = document.getElementById("result");

  if (res.ok) {
    resultEl.innerText = "Login successful!";

    // ✅ Store username and user_id
    chrome.storage.local.set({
      username: username,
      userId: result.user_id
    }, () => {
      document.getElementById("user").innerHTML = `User : ${username}`;
      document.getElementById("login-page").hidden = true;
      document.getElementById("main-page").hidden = false;
    });

  } else {
    resultEl.innerText = result.detail || "Login failed.";
  }
}

async function handleLogout() {
    chrome.storage.local.clear(() => {
      console.log("User data cleared.");
      document.getElementById("login-page").hidden = false;
      document.getElementById("main-page").hidden = true;
    });
}


document.getElementById("loginBtn").onclick = handleLogin;
document.getElementById("logout-btn").onclick = handleLogout;
document.getElementById("auth-btn").onclick = authenticate;
document.getElementById("refresh-btn").onclick = refreshIngestionStatus;
document.getElementById("submit-btn").onclick = submitQuery;
