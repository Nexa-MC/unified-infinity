#!/usr/bin/env python3
"""Bind the frozen semantic verifier to an independently supplied consumer boundary.
This adapter does not modify the executed compiler, reviewed contract, or original receipts.
"""
import argparse,pathlib,json
from portable_io import canonical,load,require
from validate_portable import validate,pin

def validate_for_consumer(receipt,contract,contract_sha256,consumer_root):
 root=canonical(consumer_root,kind='directory');receipt=canonical(receipt,root);data=load(receipt)
 require(data.get('consumerRoot')==str(root),'receipt consumerRoot differs from caller boundary')
 result=validate(receipt,contract,contract_sha256)
 result['callerConsumerRoot']=str(root)
 result['consumerBoundaryValidator']=pin(__file__)
 return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--receipt',required=True,type=pathlib.Path);p.add_argument('--contract',required=True,type=pathlib.Path);p.add_argument('--contract-sha256',required=True);p.add_argument('--consumer-root',required=True,type=pathlib.Path);p.add_argument('--output',required=True,type=pathlib.Path);args=p.parse_args()
 out=canonical(args.output,canonical(args.consumer_root,kind='directory'),missing=True);require(not out.exists(),'fresh boundary validation output')
 result=validate_for_consumer(args.receipt,args.contract,args.contract_sha256,args.consumer_root)
 out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
