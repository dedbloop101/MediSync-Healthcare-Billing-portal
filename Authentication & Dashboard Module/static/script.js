document.addEventListener("DOMContentLoaded", function () {
  const flipCard = document.getElementById("flip-card");

  function toggleForm(event) {
    event.preventDefault();
    flipCard.classList.toggle("flipped");
  }

  // Toggle form buttons
  document.querySelectorAll(".toggle-btn").forEach((button) => {
    button.addEventListener("click", toggleForm);
  });

  // Handle Registration
  const registerForm = document.getElementById("registerForm");
  const passwordInput = document.getElementById("reg-password");
  const passwordStrength = document.getElementById("password-strength");

  passwordInput.addEventListener("input", function () {
    const strength = getPasswordStrength(passwordInput.value);
    passwordStrength.innerHTML = `Strength: ${strength}`;
  });

  registerForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const data = new URLSearchParams();
    data.append("name", document.getElementById("reg-name").value);
    data.append("dob", document.getElementById("reg-dob").value);
    data.append("email", document.getElementById("reg-email").value);
    data.append("password", passwordInput.value);
    
    // NEW: Capture the role from the dropdown
    const roleSelect = document.getElementById("reg-role");
    data.append("role", roleSelect.value);

    fetch("/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: data,
    })
      .then((response) => {
        if (response.redirected) {
          window.location.href = response.url;
        } else {
          return response.json();
        }
      })
      .then((data) => {
        if (data && data.message) alert(data.message);
      })
      .catch(() => alert("Registration failed"));
  });

  // Handle Login
  const loginForm = document.getElementById("loginForm");
  loginForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const data = new URLSearchParams();
    data.append("email", document.getElementById("login-email").value);
    data.append("password", document.getElementById("login-password").value);

    fetch("/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: data,
    })
      .then((res) => res.json())
      .then((data) => {
        if (data.success) {
          window.location.href = data.redirect || "/";
        } else {
          alert(data.message);
        }
      })
      .catch(() => alert("Login failed"));
  });

  function getPasswordStrength(password) {
    const lengthCriteria = password.length >= 8;
    const upperCase = /[A-Z]/.test(password);
    const lowerCase = /[a-z]/.test(password);
    const number = /[0-9]/.test(password);
    const specialChar = /[!@#$%^&*(),.?":{}|<>]/.test(password);

    let strength = "Weak";
    if (lengthCriteria && upperCase && lowerCase && number && specialChar) {
      strength = "Strong";
    } else if (lengthCriteria && (upperCase || lowerCase) && (number || specialChar)) {
      strength = "Medium";
    }
    return strength;
  }
});