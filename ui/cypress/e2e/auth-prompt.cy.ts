describe("Authentication prompt", () => {
  it("shows the auth gate when no token is present", () => {
    cy.visit("/");
    cy.contains("Sign In").should("be.visible");
    cy.contains("Authenticate").should("be.visible");
    cy.contains("Enter domain and token. Domain is required for non-admin authentication.").should("be.visible");
  });
});
