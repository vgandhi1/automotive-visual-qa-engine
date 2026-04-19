{
  "Comment": "Anomaly → rework routing (MVP: router then SAP)",
  "StartAt": "ReworkRouter",
  "States": {
    "ReworkRouter": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${rework_router_arn}",
        "Payload.$": "$"
      },
      "ResultPath": "$.lambda_out",
      "Next": "SAPIntegration",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "Fail"
        }
      ]
    },
    "SAPIntegration": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke",
      "Parameters": {
        "FunctionName": "${sap_integration_arn}",
        "Payload": {
          "vlm.$": "$.vlm",
          "edge.$": "$.edge",
          "plant_location.$": "$.lambda_out.Payload.plant_location",
          "vin.$": "$.edge.vin"
        }
      },
      "ResultPath": "$.sap_lambda_out",
      "Next": "Success",
      "Catch": [
        {
          "ErrorEquals": ["States.ALL"],
          "ResultPath": "$.error",
          "Next": "Fail"
        }
      ]
    },
    "Success": { "Type": "Succeed" },
    "Fail": { "Type": "Fail", "Error": "ReworkRoutingFailed" }
  }
}
