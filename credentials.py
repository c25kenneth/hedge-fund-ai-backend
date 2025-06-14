from azure.identity import DefaultAzureCredential
token = DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")
print("Token retrieved successfully:", token.token[:10])  # for debug
